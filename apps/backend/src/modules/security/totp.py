import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
ISSUER = "M&A CRM"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def _code_at_step(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def totp_code(secret: str, at: datetime) -> str:
    return _code_at_step(secret, int(at.timestamp()) // STEP_SECONDS)


def verify_totp(secret: str, code: str, at: datetime) -> bool:
    step = int(at.timestamp()) // STEP_SECONDS
    candidate = code.strip().replace(" ", "")
    return any(hmac.compare_digest(_code_at_step(secret, step + drift), candidate) for drift in (-1, 0, 1))


def provisioning_uri(secret: str, account: str) -> str:
    return f"otpauth://totp/{quote(ISSUER)}:{quote(account)}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={STEP_SECONDS}"
