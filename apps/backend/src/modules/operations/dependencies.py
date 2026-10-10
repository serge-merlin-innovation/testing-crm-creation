from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import OperationsService


def get_operations_service(notifications: NotificationServiceDep) -> OperationsService:
    return OperationsService(notifications)


OperationsServiceDep = Annotated[OperationsService, Depends(get_operations_service)]
