from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import OriginationService


def get_origination_service(notifications: NotificationServiceDep) -> OriginationService:
    return OriginationService(notifications)


OriginationServiceDep = Annotated[OriginationService, Depends(get_origination_service)]
