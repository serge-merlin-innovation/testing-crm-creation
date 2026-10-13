from typing import Annotated

from fastapi import Depends

from ...infrastructure.email import EmailSender, get_email_sender
from .service import NotificationService


def get_notification_service(sender: Annotated[EmailSender, Depends(get_email_sender)]) -> NotificationService:
    return NotificationService(sender)


NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
