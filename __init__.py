"""JDECo Home Assistant Integration."""

from __future__ import annotations
import asyncio
import logging
import secrets
import ssl

import aiohttp
from aiohttp import TCPConnector
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .client import JDecoClient, AuthError, CannotConnect
from .coordinator import JDecoCoordinator
from .crypto import rsa_private_key_to_pem, rsa_private_key_from_pem, generate_rsa_keypair
from .const import (
    DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_DEVID,
    CONF_GID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL,
)

from .proxy_connector import ProxyConnector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Temporary Tor proxy flag for initial setup and bypassing temporary Cloudflare block.
# Set to False once device token is registered to restore high-speed direct connection.
USE_TOR_PROXY = False
TOR_SOCKS5_HOST = "127.0.0.1"
TOR_SOCKS5_PORT = 9050

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "button"]


def create_tor_session() -> aiohttp.ClientSession:
    """Create an aiohttp ClientSession routed through Tor SOCKS5."""
    connector = ProxyConnector.from_url(f"socks5://{TOR_SOCKS5_HOST}:{TOR_SOCKS5_PORT}")
    return aiohttp.ClientSession(connector=connector)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up JDECo integration (YAML not used, config_flow only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    devid    = entry.data.get(CONF_DEVID)
    gid      = entry.data.get(CONF_GID)
    interval = entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    if not devid or not gid:
        _LOGGER.error("JDECo entry %s missing devid or gid — re-authentication required", entry.entry_id)
        raise ConfigEntryAuthFailed("JDECo device not registered. Please re-authenticate.")

    # ── Persistent RSA key store (10-day lifecycle matching APK f7.g.q()) ──
    store = Store(hass, 1, f"jdeco_keys_{entry.entry_id}")
    stored_keys = await store.async_load() or {}

    # Check if fresh keys were supplied during setup from config_flow
    entry_priv_pem = entry.data.get("client_private_key_pem")
    entry_server_pk = entry.data.get("server_public_key_xml")

    if entry_priv_pem and not stored_keys.get("client_private_key_pem"):
        stored_keys = {
            "client_private_key_pem": entry_priv_pem,
            "server_public_key_xml": entry_server_pk or "",
            "devid": devid,
            "gid": gid,
        }
        await store.async_save(stored_keys)
        _LOGGER.info("Saved JDECo client keys from config flow into persistent storage.")

        # Clean private key from config entry data so it resides only in protected store
        clean_data = {k: v for k, v in entry.data.items() if k not in ("client_private_key_pem", "server_public_key_xml")}
        hass.config_entries.async_update_entry(entry, data=clean_data)

    client_priv = None
    server_pk_xml = stored_keys.get("server_public_key_xml", "")

    if "client_private_key_pem" in stored_keys:
        try:
            client_priv = rsa_private_key_from_pem(stored_keys["client_private_key_pem"])
            _LOGGER.info("JDECo loaded persistent client RSA keypair from storage.")
        except Exception as err:
            _LOGGER.warning("Could not load stored client RSA key: %s", err)

    if client_priv is None:
        _LOGGER.error("No persistent RSA key found for JDECo entry %s — re-authentication required", entry.entry_id)
        raise ConfigEntryAuthFailed("Client private key missing from storage. Please re-authenticate.")

    # Session creation: Tor SOCKS5 proxy (temporary test/registration) or direct HA session
    if USE_TOR_PROXY:
        try:
            session = create_tor_session()
            _LOGGER.info("JDECo: routing via temporary Tor SOCKS5 %s:%s", TOR_SOCKS5_HOST, TOR_SOCKS5_PORT)
        except Exception as err:
            raise ConfigEntryNotReady(f"JDECo: Tor SOCKS5 proxy setup failed: {err}") from err
    else:
        session = async_get_clientsession(hass)
        _LOGGER.info("JDECo: using direct fast connection")

    client = JDecoClient(
        username, password, devid, gid, session,
        client_private_key=client_priv,
        server_public_key_xml=server_pk_xml,
    )

    try:
        await client.async_login()
    except AuthError as err:
        if USE_TOR_PROXY and not session.closed:
            await session.close()
        raise ConfigEntryAuthFailed(f"JDECo authentication failed: {err}") from err
    except (CannotConnect, Exception) as err:
        if USE_TOR_PROXY and not session.closed:
            await session.close()
        # Save any key state acquired during this attempt
        if client.client_private_key:
            try:
                await store.async_save({
                    "client_private_key_pem": rsa_private_key_to_pem(client.client_private_key),
                    "server_public_key_xml": client.server_public_key_xml,
                    "devid": devid,
                    "gid": client.gid or gid,
                })
            except Exception:
                pass
        raise ConfigEntryAuthFailed(f"JDECo connection failed: {err}") from err

    # ── Save full key state after successful login ──────────────────────────
    if client.client_private_key:
        try:
            await store.async_save({
                "client_private_key_pem": rsa_private_key_to_pem(client.client_private_key),
                "server_public_key_xml": client.server_public_key_xml,
                "devid": devid,
                "gid": client.gid or gid,
            })
        except Exception as err:
            _LOGGER.warning("Could not persist JDECo key storage: %s", err)

    agree_list = client.agree_list
    if not agree_list:
        try:
            agrees_resp = await client.async_get_user_agreements()
            agree_list = (
                agrees_resp.get("servSettings", {}).get("customerAgreements", [])
                or agrees_resp.get("customerAgreements", [])
                or []
            )
        except Exception as err:
            _LOGGER.warning("getUserAgreements fallback failed: %s", err)

    if not agree_list:
        raise ConfigEntryNotReady("No customer agreements found for this JDECo account")

    coordinators = {}
    for agreement in agree_list:
        agree_no = agreement.get("agreeNo")
        if not agree_no:
            continue
        coord = JDecoCoordinator(hass, client, agree_no, interval)
        await coord.async_config_entry_first_refresh()
        coordinators[agree_no] = coord

    hass.data[DOMAIN][entry.entry_id] = {
        "client":       client,
        "coordinators": coordinators,
        "coordinator":  next(iter(coordinators.values())) if coordinators else None,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    unload_ok  = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Only close session if we created our own Tor session (don't close HA's shared session)
        if USE_TOR_PROXY:
            client = entry_data.get("client")
            if client and hasattr(client, "_http") and not client._http.closed:
                await client._http.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry and delete persisted RSA key storage."""
    store = Store(hass, 1, f"jdeco_keys_{entry.entry_id}")
    try:
        await store.async_remove()
        _LOGGER.info("Successfully cleaned up persistent storage for JDECo entry %s", entry.entry_id)
    except Exception as err:
        _LOGGER.warning("Could not delete persistent storage for JDECo entry %s: %s", entry.entry_id, err)
