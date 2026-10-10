from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.http_exceptions import NotFoundException
from ...infrastructure.dependencies import AsyncSessionDep, CurrentSuperUserDep
from ..common.exceptions import RoleNotFoundError
from ..common.utils.error_handler import handle_exception
from .dependencies import RoleServiceDep
from .schemas import RoleRead

router = APIRouter(tags=["Roles"])


@router.get(
    "/",
    response_model=PaginatedListResponse[RoleRead],
    summary="List roles (Admin)",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not authorized - requires admin privileges"}},
)
async def get_roles(
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _: CurrentSuperUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    items_per_page: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict:
    try:
        roles_data = await role_service.get_all(
            db=db,
            skip=compute_offset(page, items_per_page),
            limit=items_per_page,
        )
        return paginated_response(crud_data=roles_data, page=page, items_per_page=items_per_page)
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get(
    "/{name}",
    response_model=RoleRead,
    summary="Get a role by name (Admin)",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized - requires admin privileges"},
        404: {"description": "Role not found"},
    },
)
async def get_role_by_name(
    name: str,
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _: CurrentSuperUserDep,
) -> dict[str, Any]:
    try:
        return await role_service.get_by_name(name, db)
    except RoleNotFoundError:
        raise NotFoundException("Role not found")
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
