from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import PrivacyService


def get_privacy_service(notifications: NotificationServiceDep) -> PrivacyService:
    return PrivacyService(notifications)


PrivacyServiceDep = Annotated[PrivacyService, Depends(get_privacy_service)]
