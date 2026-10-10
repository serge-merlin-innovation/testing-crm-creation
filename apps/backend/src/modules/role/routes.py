from typing import Annotated, Any

from fastapi import APIRouter, Response

from ...infrastructure.dependencies import AsyncSessionDep
from ..audit.dependencies import AuditContextDep
from .authorization import require_permission
from .dependencies import RoleServiceDep
from .permissions import Permission
from .schemas import PermissionMatrix, RolePermissionsUpdate, RoleRead

router = APIRouter(tags=["Roles"])

RoleManagerDep = Annotated[dict[str, Any], require_permission(Permission.ROLES_MANAGE)]


@router.get("/", response_model=list[RoleRead], summary="List roles (Admin)")
async def get_roles(db: AsyncSessionDep, role_service: RoleServiceDep, _: RoleManagerDep) -> list[dict[str, Any]]:
    return await role_service.list_roles(db)


@router.get(
    "/matrix",
    response_model=PermissionMatrix,
    summary="Permission matrix (Admin)",
    description="Roles are columns, permissions are rows; `granted[i]` belongs to `columns[i]`.",
)
async def get_permission_matrix(db: AsyncSessionDep, role_service: RoleServiceDep, _: RoleManagerDep) -> PermissionMatrix:
    return await role_service.matrix(db)


@router.get(
    "/matrix/export",
    summary="Export the permission matrix as CSV (Admin)",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_permission_matrix(
    db: AsyncSessionDep, role_service: RoleServiceDep, context: AuditContextDep, _: RoleManagerDep
) -> Response:
    body = await role_service.export_matrix_csv(db, context)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="permission-matrix.csv"'},
    )


@router.put(
    "/{role_id}/permissions",
    response_model=RoleRead,
    summary="Replace a role's permissions (Admin)",
    description="Applies at every holder's next request and is written to the audit log.",
)
async def set_role_permissions(
    role_id: int,
    values: RolePermissionsUpdate,
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    context: AuditContextDep,
    _: RoleManagerDep,
) -> dict[str, Any]:
    return await role_service.set_permissions(role_id, values, db, context)
