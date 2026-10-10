from dataclasses import dataclass
from typing import Protocol

from ..logging import get_logger

logger = get_logger()


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class LoggingEmailSender:
    async def send(self, message: EmailMessage) -> None:
        logger.info(f"Email to {message.to}: {message.subject}")


class InMemoryEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def to(self, address: str) -> list[EmailMessage]:
        return [message for message in self.sent if message.to == address]


_sender: EmailSender = LoggingEmailSender()


def get_email_sender() -> EmailSender:
    return _sender


def set_email_sender(sender: EmailSender) -> None:
    global _sender
    _sender = sender
