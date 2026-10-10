from dataclasses import dataclass
from typing import Protocol

from ...infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    async def send(self, email: SentEmail) -> None: ...


class LoggingEmailSender:
    """Stands in until the outbound mail adapter (ACS/Resend) is wired: logs the recipient only."""

    async def send(self, email: SentEmail) -> None:
        logger.info("Email queued for %s: %s", email.to, email.subject)
