from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .pipeline import PipelineService
from .service import MandateService


def get_mandate_service(notifications: NotificationServiceDep) -> MandateService:
    return MandateService(notifications)


MandateServiceDep = Annotated[MandateService, Depends(get_mandate_service)]


def get_pipeline_service(notifications: NotificationServiceDep) -> PipelineService:
    return PipelineService(notifications)


PipelineServiceDep = Annotated[PipelineService, Depends(get_pipeline_service)]
