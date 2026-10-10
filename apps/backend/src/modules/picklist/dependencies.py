from typing import Annotated

from fastapi import Depends

from .service import PicklistService


def get_picklist_service() -> PicklistService:
    return PicklistService()


PicklistServiceDep = Annotated[PicklistService, Depends(get_picklist_service)]
