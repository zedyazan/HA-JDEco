"""JDECo config flow."""

from __future__ import annotations
import secrets
import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_DEVID, CONF_GID,
    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL,
)
from .client import (
    JDecoClient,
    AuthError,
    DeviceNotRegisteredError,
    CannotConnect,
    ProtocolError,
)

from .crypto import generate_rsa_keypair, rsa_private_key_to_pem

_LOGGER = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    """Mask phone number for safe logging."""
    if not phone or len(phone) < 4:
        return "***"
    return f"{phone[:3]}***{phone[-2:]}"


class JDecoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._client: JDecoClient | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            # Generate fresh, unique device identity and RSA keypair for this user
            devid = secrets.token_hex(8)
            client_priv, _ = generate_rsa_keypair()
            priv_pem = rsa_private_key_to_pem(client_priv)

            self._data = {
                CONF_USERNAME:            username,
                CONF_PASSWORD:            password,
                CONF_DEVID:               devid,
                CONF_GID:                 "",
                CONF_SCAN_INTERVAL:       interval,
                "client_private_key_pem": priv_pem,
            }

            session = async_get_clientsession(self.hass)
            self._client = JDecoClient(
                username, password, devid, "", session,
                client_private_key=client_priv,
            )

            # Directly request SMS OTP to authorize this new device
            _LOGGER.info("Initiating JDECo registration for %s (devid=%s)...", _mask_phone(username), devid)
            try:
                await self._client.async_request_verification_code(username)
            except AuthError as err:
                _LOGGER.warning("JDECo SMS request auth error: %s", err)
                errors["base"] = "invalid_auth"
            except CannotConnect as err:
                _LOGGER.warning("JDECo cannot connect during SMS request: %s", err)
                errors["base"] = "cannot_connect"
            except ProtocolError as err:
                _LOGGER.error("JDECo protocol error during SMS request: %s", err)
                errors["base"] = "protocol_error"
            except Exception as err:
                _LOGGER.exception("Unexpected error during JDECo SMS request: %s", err)
                errors["base"] = "unknown"
            else:
                self._data["server_public_key_xml"] = self._client.server_public_key_xml
                return await self.async_step_otp()

        schema = vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
                vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_otp(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            otp = user_input["otp"].strip()
            try:
                res = await self._client.async_verify_mobile_number(
                    self._data[CONF_USERNAME], otp
                )
                self._data[CONF_GID] = res["dlasck"]
                if res.get("username") and str(res["username"]).strip():
                    self._data[CONF_USERNAME] = str(res["username"]).strip()
                self._client._username = self._data[CONF_USERNAME]
                self._client._password = self._data[CONF_PASSWORD]
                self._data["server_public_key_xml"] = self._client.server_public_key_xml

                # Verify customer credentials to ensure password is valid
                await self._client.async_login()
            except AuthError as err:
                _LOGGER.warning("JDECo OTP or credential verification failed: %s", err)
                if "password" in str(err).lower() or "50016" in str(err):
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "invalid_otp"
            except CannotConnect as err:
                _LOGGER.warning("JDECo connection failed during OTP verification: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error during JDECo OTP verification: %s", err)
                errors["base"] = "unknown"
            else:
                existing_entry = await self.async_set_unique_id(self._data[CONF_USERNAME].lower())
                if existing_entry:
                    return self.async_update_reload_and_abort(existing_entry, data=self._data)
                return self.async_create_entry(
                    title=f"JDECo ({self._data[CONF_USERNAME]})",
                    data=self._data,
                )

        schema = vol.Schema({
            vol.Required("otp"): str,
        })

        return self.async_show_form(
            step_id="otp",
            data_schema=schema,
            description_placeholders={"phone": self._data.get(CONF_USERNAME, "")},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Handle re-authentication triggered by ConfigEntryAuthFailed."""
        self._data = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        """Confirm reauth and trigger SMS verification."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = self._data[CONF_USERNAME]
            password = self._data[CONF_PASSWORD]
            devid    = secrets.token_hex(8)
            client_priv, _ = generate_rsa_keypair()
            priv_pem = rsa_private_key_to_pem(client_priv)

            self._data[CONF_DEVID] = devid
            self._data[CONF_GID]   = ""
            self._data["client_private_key_pem"] = priv_pem

            session = async_get_clientsession(self.hass)
            self._client = JDecoClient(
                username, password, devid, "", session,
                client_private_key=client_priv,
            )
            try:
                await self._client.async_request_verification_code(username)
            except Exception as err:
                _LOGGER.error("Failed to request JDECo verification code during reauth: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._data["server_public_key_xml"] = self._client.server_public_key_xml
                return await self.async_step_otp()

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"phone": self._data.get(CONF_USERNAME, "")},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return JDecoOptionsFlow()


class JDecoOptionsFlow(config_entries.OptionsFlow):

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        schema = vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=current_interval):
                vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
