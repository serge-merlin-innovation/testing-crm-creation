from typing import Annotated

from fastapi import Depends

from .ports import EmailSender, LoggingEmailSender
from .service import NotificationService


def get_email_sender() -> EmailSender:
    return LoggingEmailSender()


def get_notification_service(sender: Annotated[EmailSender, Depends(get_email_sender)]) -> NotificationService:
    return NotificationService(sender)


NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
