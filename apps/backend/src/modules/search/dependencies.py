from typing import Annotated

from fastapi import Depends

from .service import SavedFilterService, SearchService


def get_search_service() -> SearchService:
    return SearchService()


def get_saved_filter_service() -> SavedFilterService:
    return SavedFilterService()


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
SavedFilterServiceDep = Annotated[SavedFilterService, Depends(get_saved_filter_service)]
