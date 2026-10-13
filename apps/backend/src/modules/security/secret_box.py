import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from ...infrastructure.config.settings import settings


def _fernet() -> Fernet:
    material = settings.TOTP_ENCRYPTION_KEY or f"totp:{settings.SECRET_KEY}"
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))


def seal_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def open_secret(sealed: str) -> str:
    try:
        return _fernet().decrypt(sealed.encode()).decode()
    except InvalidToken as error:
        raise ValueError("TOTP secret cannot be decrypted with TOTP_ENCRYPTION_KEY") from error


class EncryptedString(TypeDecorator[str]):
    """Stored as a Fernet token; the Python value is the plaintext."""

    impl = String(255)
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else seal_secret(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else open_secret(value)
