from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import ImportService


def get_import_service(notifications: NotificationServiceDep) -> ImportService:
    return ImportService(notifications)


ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]
