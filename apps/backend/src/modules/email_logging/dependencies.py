import hmac
from typing import Annotated, Any

from crudauth.exceptions import UnauthorizedException
from fastapi import Depends, Header

from ...infrastructure.config.settings import settings
from .service import EmailLoggingService


def get_email_logging_service() -> EmailLoggingService:
    return EmailLoggingService()


def require_inbound_secret(x_inbound_secret: Annotated[str, Header()] = "") -> None:
    """The mail provider's inbound-parse webhook proves itself with a shared secret."""
    expected = settings.INBOUND_EMAIL_SECRET
    if not expected or not hmac.compare_digest(x_inbound_secret.encode(), expected.encode()):
        raise UnauthorizedException("Invalid inbound webhook secret")


EmailLoggingServiceDep = Annotated[EmailLoggingService, Depends(get_email_logging_service)]
InboundSecretDep = Annotated[Any, Depends(require_inbound_secret)]
