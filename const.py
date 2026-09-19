"""Constants for the JDECo integration — confirmed from APK bytecode."""

from __future__ import annotations

DOMAIN = "jdeco"

# Server constants (confirmed: 03_COMPLETE_PROTOCOL.md, 08_PROTOCOL_VERIFICATION.md)
BASE_URL      = "https://androidAPP.jdeco.net:2083/V3GACG"
SYSTEM_ID     = 204
PRE_LOGIN_KEY = "3c0b391821ee2bab1367c0b7a34a0114"
APP_VERSION   = "5.3.1"
TIMEOUT_AUTH  = 40    # seconds — confirmed: LoginActivity.z1()/x1() u5Var.y=40000
TIMEOUT_DATA  = 90    # seconds — confirmed: h3.l0() u5Var.y=90000

# Hardcoded server RSA-2048 bootstrap public key (03_COMPLETE_PROTOCOL.md §1)
SERVER_BOOTSTRAP_MODULUS_B64 = (
    "uB2DGLlQY8BngYmqZsl6/amB1tBOb4NFO2+r3ehYmkiv8q+FaRbfypw8Nap21SJN"
    "gnvM46KluS0PiclEfSFGRo7kkmmohIM5pFaQulFdDYMkfvexqOlhATzOTm2SpzHg"
    "e9EpGMLuyy9CLaWNVxGwmwU/yEcOlusenDgFrD0hY5r9jNUlqlYdJlJVh6z/8S7L"
    "6gyrKrvSr1bcuIj1AhQHw4sPW9T7IaM5HOaHrwk8mpd4b/8QtHx7VV9Ed2n0OeKi"
    "q3apQX8pfn/i7Qd6a5VOprB7HvrHuaGtAlbfb4S36q+vjPgTqXjd5mrAE0D8Roki"
    "2jeUZnNjCreRHwCw7tJVhw=="
)

# Result codes
RESULT_OK      = 0
RESULT_AUTH_OK = 1000  # verified from APK m0.java line 485: verifyCustomerCredentials success code
RESULT_NO_DATA = 602   # normal for prepaid getAgreeDebt (no postpaid debt)
RESULT_EXPIRED = 1021  # session expired — re-login required

# Config entry keys
CONF_USERNAME      = "username"
CONF_PASSWORD      = "password"
CONF_DEVID         = "devid"
CONF_GID           = "gid"
CONF_SCAN_INTERVAL = "scan_interval"

# Defaults
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL     = 30
MAX_SCAN_INTERVAL     = 1440

# HTTP & Rate-Limiting
REQUEST_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "User-Agent": "okhttp/4.12.0",
    "Connection": "close",
}
MIN_REQUEST_GAP = 2.5   # minimum seconds between any consecutive HTTP requests
LOGIN_COOLDOWN  = 60.0  # minimum seconds between login attempts

