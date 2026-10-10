from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import AccessService


def get_access_service(notifications: NotificationServiceDep) -> AccessService:
    return AccessService(notifications)


AccessServiceDep = Annotated[AccessService, Depends(get_access_service)]
