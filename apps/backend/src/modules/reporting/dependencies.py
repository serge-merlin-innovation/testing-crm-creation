from typing import Annotated

from fastapi import Depends

from .service import ReportingService


def get_reporting_service() -> ReportingService:
    return ReportingService()


ReportingServiceDep = Annotated[ReportingService, Depends(get_reporting_service)]
