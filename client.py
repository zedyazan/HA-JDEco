"""JDECo API client — AES-256-GCM + RSA-2048/PKCS1v15 wire protocol."""
from __future__ import annotations
import asyncio, base64, json, logging, os, time
from datetime import datetime

import aiohttp
from cryptography.hazmat.primitives.asymmetric import rsa

from .const import (
    BASE_URL, SYSTEM_ID, PRE_LOGIN_KEY, APP_VERSION,
    TIMEOUT_AUTH, TIMEOUT_DATA, REQUEST_HEADERS,
    RESULT_OK, RESULT_AUTH_OK, RESULT_EXPIRED,
    SERVER_BOOTSTRAP_MODULUS_B64, MIN_REQUEST_GAP, LOGIN_COOLDOWN,
)
from .crypto import (
    generate_rsa_keypair, build_bootstrap_server_key,
    rsa_public_key_to_dotnet_xml, rsa_public_key_from_dotnet_xml,
    encrypt_request, decrypt_response,
)

_LOGGER = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    """Mask phone number for safe logging."""
    if not phone or len(phone) < 4:
        return "***"
    return f"{phone[:3]}***{phone[-2:]}"


class AuthError(Exception):
    """Authentication failure."""

class DeviceNotRegisteredError(AuthError):
    """Server returned 607 — device needs SMS registration."""

class CannotConnect(Exception):
    """Network / timeout failure."""

class ProtocolError(Exception):
    """Decryption or unexpected response format."""


class _State:
    def __init__(self):
        self.client_private_key: rsa.RSAPrivateKey | None = None
        self.client_public_key:  rsa.RSAPublicKey  | None = None
        self.server_public_key:  rsa.RSAPublicKey  | None = None
        self.server_public_key_xml: str = ""
        self.session_key: str = ""
        self.agree_list: list = []
        self.consecutive_1021: int = 0

    @property
    def authenticated(self) -> bool:
        return bool(self.session_key)

    def clear_session(self):
        self.session_key = ""
        self.agree_list = []
        self.consecutive_1021 = 0


def _frf(devid: str) -> str:
    # APK a.E(): android_id + "_" + SimpleDateFormat("ddMMyy", Locale("en"))
    return devid + "_" + datetime.now().strftime("%d%m%y")


def _common(auth_key: str, devid: str, gid: str | None = None) -> dict:
    auth: dict = {"systemID": SYSTEM_ID, "authKey": auth_key}
    if gid:
        auth["GID"] = gid
    return {"auth": auth, "DEVID": devid, "APPVersionName": APP_VERSION, "FRF": _frf(devid)}


class JDecoClient:
    def __init__(
        self,
        username: str, password: str, devid: str, gid: str,
        http_session: aiohttp.ClientSession,
        client_private_key: rsa.RSAPrivateKey | None = None,
        server_public_key_xml: str = "",
    ):
        self._username = username
        self._password = password
        self._devid    = devid
        self._gid      = gid
        self._http     = http_session
        self._s        = _State()
        self._last_req:   float = 0.0
        self._last_login: float = 0.0

        if client_private_key:
            self._s.client_private_key = client_private_key
            self._s.client_public_key  = client_private_key.public_key()
        if server_public_key_xml:
            try:
                self._s.server_public_key     = rsa_public_key_from_dotnet_xml(server_public_key_xml)
                self._s.server_public_key_xml = server_public_key_xml
            except Exception as err:
                _LOGGER.warning("Cannot parse cached server key: %s", err)

    # ── internal helpers ────────────────────────────────────────────────────

    async def _post(self, method: str, body: dict, srv_pk, cli_priv, timeout: int) -> dict:
        gap = MIN_REQUEST_GAP - (time.monotonic() - self._last_req)
        if gap > 0:
            await asyncio.sleep(gap)
        self._last_req = time.monotonic()

        http_body = encrypt_request(json.dumps(body, separators=(",", ":")), srv_pk, self._devid)
        raw = ""
        for attempt in range(3):
            try:
                async with self._http.post(
                    f"{BASE_URL}/{method}",
                    data=http_body.encode("utf-8"),
                    headers=REQUEST_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    ssl=True,
                ) as resp:
                    raw = await resp.text(encoding="utf-8")
                    _LOGGER.debug("RESP %s status=%d len=%d", method, resp.status, len(raw))
                    if not raw or not raw.strip():
                        if method == "verifyCustomerCredentials":
                            raise DeviceNotRegisteredError("Device not registered or GID expired (server returned empty response)")
                        raise CannotConnect(f"Empty response for {method} (HTTP {resp.status})")
                    if resp.status >= 400:
                        raise aiohttp.ClientResponseError(resp.request_info, resp.history,
                                                          status=resp.status, message=raw[:200])
                    break
            except DeviceNotRegisteredError:
                raise
            except (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError, asyncio.TimeoutError) as err:
                if attempt < 2:
                    _LOGGER.info("Server disconnected/timeout during %s (attempt %d/3) — retrying in %ds...",
                                 method, attempt + 1, attempt + 1)
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise CannotConnect(f"JDECo server communication error during {method}: {err}") from err
            except aiohttp.ClientError as err:
                raise CannotConnect(f"JDECo network error ({method}): {err}") from err

        try:
            plain = decrypt_response(raw, cli_priv)
        except Exception as err:
            _LOGGER.error("Decrypt failed %s: %s | raw=%s", method, err, raw[:200])
            raise ProtocolError(f"Decrypt failed {method}: {err}") from err

        try:
            parsed = json.loads(plain)
        except json.JSONDecodeError as err:
            raise ProtocolError(f"Invalid JSON from {method}: {err}") from err

        return parsed.get(f"{method}Result", parsed)

    async def _request_pk(self):
        if not self._s.client_private_key:
            priv, pub = generate_rsa_keypair()
            self._s.client_private_key = priv
            self._s.client_public_key  = pub

        body = _common(PRE_LOGIN_KEY, self._devid)
        body["PK"]   = rsa_public_key_to_dotnet_xml(self._s.client_public_key)
        body["stsb"] = base64.b64encode(os.urandom(32)).decode()

        res = await self._post("requestPK", body,
                               build_bootstrap_server_key(SERVER_BOOTSTRAP_MODULUS_B64),
                               self._s.client_private_key, TIMEOUT_AUTH)
        if res.get("resultCode", -1) != RESULT_OK:
            raise AuthError(f"requestPK failed ({res.get('resultCode')}): {res.get('resultStringE','')}")

        xml = res.get("value", "")
        if not xml:
            raise ProtocolError("requestPK missing 'value'")
        self._s.server_public_key     = rsa_public_key_from_dotnet_xml(xml)
        self._s.server_public_key_xml = xml
        _LOGGER.info("requestPK OK — server key updated")

    async def _verify_credentials(self):
        body = _common(PRE_LOGIN_KEY, self._devid, self._gid or None)
        body["userName"] = self._username.strip()
        body["password"] = self._password
        _LOGGER.info("verifyCustomerCredentials user=%s gid=%s...", _mask_phone(self._username), self._gid[:8] if self._gid else "")

        res = await self._post("verifyCustomerCredentials", body,
                               self._s.server_public_key, self._s.client_private_key, TIMEOUT_AUTH)
        code = res.get("resultCode", -1)
        msg  = res.get("resultStringE") or res.get("resultStringA", "")
        _LOGGER.info("verifyCustomerCredentials → code=%s %s", code, msg)

        if code == 607:   raise DeviceNotRegisteredError(f"Device not registered ({code}): {msg}")
        if code == 50016: raise AuthError(f"Wrong password ({code})")
        if code not in (RESULT_OK, RESULT_AUTH_OK):
            raise AuthError(f"Login failed ({code}): {msg}")

        jrf = res.get("trans", {}).get("JRF", 0)
        if not jrf:
            raise AuthError(f"Invalid JRF token: {jrf}")
        self._s.session_key  = str(jrf)
        self._s.agree_list   = res.get("servSettings", {}).get("customerAgreements", [])
        self._s.consecutive_1021 = 0

        # Adopt server-assigned GID if provided
        try:
            extra = json.loads(res.get("servSettings", {}).get("extraSettingsS", "") or "{}")
            if isinstance(extra, dict) and extra.get("GID"):
                self._gid = str(extra["GID"])
        except Exception:
            pass

        _LOGGER.info("Authenticated as %s — %d agreement(s)", _mask_phone(self._username), len(self._s.agree_list))

    # ── public API ──────────────────────────────────────────────────────────

    @property
    def client_private_key(self) -> rsa.RSAPrivateKey | None:
        return self._s.client_private_key

    @property
    def server_public_key_xml(self) -> str:
        return self._s.server_public_key_xml

    @property
    def agree_list(self) -> list:
        return self._s.agree_list

    @property
    def is_authenticated(self) -> bool:
        return self._s.authenticated

    @property
    def gid(self) -> str:
        return self._gid

    @property
    def devid(self) -> str:
        return self._devid

    @property
    def username(self) -> str:
        return self._username

    async def async_login(self):
        """Full login with cooldown enforcement. Skips requestPK if server key cached."""
        gap = LOGIN_COOLDOWN - (time.monotonic() - self._last_login)
        if self._last_login > 0 and gap > 0:
            _LOGGER.info("Login cooldown: waiting %ds", int(gap))
            await asyncio.sleep(gap)
        self._last_login = time.monotonic()
        self._s.clear_session()

        if not self._s.client_private_key:
            priv, pub = generate_rsa_keypair()
            self._s.client_private_key = priv
            self._s.client_public_key  = pub

        if self._s.server_public_key:
            try:
                _LOGGER.info("Fast login with cached server key...")
                await self._verify_credentials()
                return
            except (CannotConnect, ProtocolError) as err:
                _LOGGER.warning("Fast login failed (%s) — retrying via requestPK", err)
            except (AuthError, DeviceNotRegisteredError):
                raise

        await self._request_pk()
        await self._verify_credentials()

    async def async_request_verification_code(self, mobile_number: str) -> dict:
        """Request SMS OTP. Blocked if DLASCK already exists (safety guard)."""
        if self._gid:
            raise AuthError("DLASCK present — new SMS blocked to protect account.")
        if not self._s.server_public_key:
            await self._request_pk()
        body = _common(PRE_LOGIN_KEY, self._devid)
        body["mobileNumber"] = mobile_number.strip()
        res = await self._post("requestVerificationCode", body,
                               self._s.server_public_key, self._s.client_private_key, TIMEOUT_AUTH)
        code = res.get("resultCode", -1)
        if code not in (RESULT_OK, 50000):
            raise AuthError(f"SMS request failed ({code}): {res.get('resultStringE','')}")
        return res

    async def async_verify_mobile_number(self, mobile_number: str, otp: str) -> dict[str, str]:
        """Verify SMS OTP → returns DLASCK token."""
        if not self._s.server_public_key:
            await self._request_pk()
        body = _common(PRE_LOGIN_KEY, self._devid)
        body.update({"mobileNumber": mobile_number.strip(), "verificationCode": otp.strip(), "regID": ""})
        res = await self._post("verifyMobileNumber", body,
                               self._s.server_public_key, self._s.client_private_key, TIMEOUT_AUTH)
        if res.get("resultCode", -1) != RESULT_OK:
            raise AuthError(f"OTP verify failed ({res.get('resultCode')}): {res.get('resultStringE','')}")

        val = res.get("value")
        dlasck = ""
        if isinstance(val, list):
            dlasck = str(val[2] if len(val) >= 3 else val[0])
            if len(val) >= 1 and val[0] and str(val[0]).strip():
                self._username = str(val[0]).strip()
        elif isinstance(val, str):
            dlasck = val
        if not dlasck:
            raise ProtocolError(f"verifyMobileNumber missing DLASCK: {res}")

        if not self._username:
            self._username = mobile_number.strip()

        self._gid = dlasck
        _LOGGER.info("Mobile verified — DLASCK obtained, username=%s", _mask_phone(self._username))
        return {"dlasck": dlasck, "username": self._username}

    async def async_call(self, method: str, extra: dict | None = None) -> dict:
        """Authenticated API call with auto re-login on session expiry."""
        if not self._s.authenticated or not self._s.server_public_key:
            await self.async_login()
        auth_key = self._s.session_key or PRE_LOGIN_KEY
        body = _common(auth_key, self._devid, self._gid)
        if extra:
            body.update(extra)
        res = await self._post(method, body, self._s.server_public_key,
                               self._s.client_private_key, TIMEOUT_DATA)
        if res.get("resultCode") == RESULT_EXPIRED:
            self._s.consecutive_1021 += 1
            if self._s.consecutive_1021 > 3:
                raise AuthError("Session expired 3+ times — check credentials")
            _LOGGER.warning("Session expired (1021), re-authenticating (attempt %d/3)...", self._s.consecutive_1021)
            self._s.clear_session()
            await self.async_login()
            return await self.async_call(method, extra)
        self._s.consecutive_1021 = 0
        return res

    # ── data endpoints ──────────────────────────────────────────────────────

    async def async_get_agreement(self, agree_no: str) -> dict:
        return await self.async_call("getUserAgreement", {
            "username": self._username, "password": self._password,
            "agreeNo": agree_no, "IMEI": self._devid,
        })

    async def async_get_user_agreements(self) -> dict:
        return await self.async_call("getUserAgreements", {
            "username": self._username, "password": self._password,
        })

    async def async_get_kwqty(self, agree_no: str) -> dict:
        return await self.async_call("getKWQty", {"agreeNo": agree_no})

    async def async_get_debt(self, agree_no: str) -> dict:
        return await self.async_call("getAgreeDebt", {"agreeNo": agree_no})

    async def async_get_last_voucher(self, agree_no: str) -> dict:
        return await self.async_call("getAgreementLastVoucher", {"agreeNo": agree_no})

    async def async_read_smart_meter(self, agree_no: str, meter_no: str) -> dict:
        return await self.async_call("readSmartMeter", {"agreeNo": agree_no, "meterNo": meter_no})

    async def async_query_agreement_meter_and_charge(self, agree_no: str) -> dict:
        return await self.async_call("queryAgreementMeterAndCharge", {"agreeNo": agree_no})
