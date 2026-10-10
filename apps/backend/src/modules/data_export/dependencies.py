from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import DataExportService


def get_data_export_service(notifications: NotificationServiceDep) -> DataExportService:
    return DataExportService(notifications)


DataExportServiceDep = Annotated[DataExportService, Depends(get_data_export_service)]
