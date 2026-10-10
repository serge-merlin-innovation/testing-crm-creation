import csv
import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import PermissionDeniedError, RoleNotFoundError
from .models import Role
from .permissions import DEFAULT_ROLES, Permission, RoleName
from .schemas import MatrixColumn, MatrixRow, PermissionMatrix, RolePermissionsUpdate, RoleRead

# Without these the Admin role could lock every admin out of fixing permissions again.
ADMIN_LOCKED_PERMISSIONS = frozenset({Permission.ROLES_MANAGE.value, Permission.USERS_MANAGE.value})

ROLE_ORDER = [name.value for name in RoleName]


def _ordered(roles: list[Role]) -> list[Role]:
    def key(role: Role) -> tuple[int, str]:
        return (ROLE_ORDER.index(role.name) if role.name in ROLE_ORDER else len(ROLE_ORDER), role.name)

    return sorted(roles, key=key)


async def seed_default_roles(db: AsyncSession) -> list[str]:
    """Create any missing role from the role table. Existing roles, and admin edits to them, are left alone."""
    existing = set((await db.execute(select(Role.name))).scalars())
    created = []
    for name, (description, permissions) in DEFAULT_ROLES.items():
        if name.value in existing:
            continue
        db.add(Role(name=name.value, description=description, permissions=sorted(p.value for p in permissions)))
        created.append(name.value)
    await db.commit()
    return created


class RoleService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def list_roles(self, db: AsyncSession) -> list[dict[str, Any]]:
        roles = (await db.execute(select(Role).where(Role.is_deleted.is_(False)))).scalars().all()
        return [RoleRead.model_validate(role, from_attributes=True).model_dump() for role in _ordered(list(roles))]

    async def _get(self, role_id: int, db: AsyncSession) -> Role:
        role = (await db.execute(select(Role).where(Role.id == role_id, Role.is_deleted.is_(False)))).scalar_one_or_none()
        if role is None:
            raise RoleNotFoundError(f"Role with ID {role_id} not found")
        return role

    async def set_permissions(
        self, role_id: int, values: RolePermissionsUpdate, db: AsyncSession, context: AuditContext
    ) -> dict[str, Any]:
        role = await self._get(role_id, db)
        if role.name == RoleName.ADMIN.value and not ADMIN_LOCKED_PERMISSIONS <= set(values.permissions):
            raise PermissionDeniedError("The Admin role must keep roles.manage and users.manage")

        old = sorted(role.permissions)
        if old != values.permissions:
            role.permissions = list(values.permissions)
            self.audit.record(
                db,
                context,
                "role.permissions_changed",
                record_type="role",
                record_id=role.id,
                old_values={"permissions": old},
                new_values={"permissions": values.permissions},
            )
            await db.commit()
            await db.refresh(role)
        return RoleRead.model_validate(role, from_attributes=True).model_dump()

    async def matrix(self, db: AsyncSession) -> PermissionMatrix:
        roles = _ordered(list((await db.execute(select(Role).where(Role.is_deleted.is_(False)))).scalars().all()))
        return PermissionMatrix(
            columns=[MatrixColumn(id=role.id, name=role.name) for role in roles],
            rows=[
                MatrixRow(permission=permission.value, granted=[permission.value in role.permissions for role in roles])
                for permission in Permission
            ],
        )

    async def export_matrix_csv(self, db: AsyncSession, context: AuditContext) -> str:
        matrix = await self.matrix(db)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Permission", *[column.name for column in matrix.columns]])
        for row in matrix.rows:
            writer.writerow([row.permission, *["x" if granted else "" for granted in row.granted]])
        self.audit.record(db, context, "export", record_type="permission_matrix", new_values={"format": "csv"})
        await db.commit()
        return buffer.getvalue()
