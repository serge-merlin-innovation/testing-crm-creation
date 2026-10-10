from typing import Annotated

from fastapi import Depends

from ...infrastructure.auth.setup import session_transport
from .service import OffboardingService


def get_offboarding_service() -> OffboardingService:
    return OffboardingService(session_transport.clocked)


OffboardingServiceDep = Annotated[OffboardingService, Depends(get_offboarding_service)]
