from typing import Annotated

from fastapi import Depends

from .service import MergeService


def get_merge_service() -> MergeService:
    return MergeService()


MergeServiceDep = Annotated[MergeService, Depends(get_merge_service)]
