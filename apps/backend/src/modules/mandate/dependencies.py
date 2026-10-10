from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import MandateService


def get_mandate_service(notifications: NotificationServiceDep) -> MandateService:
    return MandateService(notifications)


MandateServiceDep = Annotated[MandateService, Depends(get_mandate_service)]
