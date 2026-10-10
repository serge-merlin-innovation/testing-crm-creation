from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import ConflictService, KycService


def get_conflict_service(notifications: NotificationServiceDep) -> ConflictService:
    return ConflictService(notifications)


ConflictServiceDep = Annotated[ConflictService, Depends(get_conflict_service)]


def get_kyc_service() -> KycService:
    return KycService()


KycServiceDep = Annotated[KycService, Depends(get_kyc_service)]
