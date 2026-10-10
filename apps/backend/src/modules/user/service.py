from typing import Any

from crudauth import get_password_hash
from fastcrud.types import GetMultiResponseDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import (
    LastAdminError,
    OneRolePerUserError,
    PermissionDeniedError,
    RoleNotFoundError,
    UserExistsError,
    UserNotFoundError,
)
from ..role.authorization import has_permission
from ..role.models import Role
from ..role.permissions import Permission, RoleName
from .crud import crud_users
from .models import User
from .schemas import UserAnonymize, UserCreate, UserCreateInternal, UserRead, UserRoleUpdate, UserUpdate

AUDITED_PROFILE_FIELDS = ("name", "email", "profile_image_url")


class UserService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def create(self, user: UserCreate, db: AsyncSession, context: AuditContext) -> dict[str, Any]:
        if await crud_users.exists(db=db, email=user.email):
            raise UserExistsError("Email already registered")

        internal = UserCreateInternal(name=user.name, email=user.email, hashed_password=get_password_hash(user.password))
        created = User(**internal.model_dump())
        db.add(created)
        await db.flush()
        self.audit.record(
            db,
            context,
            "user.created",
            record_type="user",
            record_id=created.id,
            new_values={"name": created.name, "email": created.email},
        )
        await db.commit()
        return await self.get_by_id(created.id, db)

    async def get_paginated(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> GetMultiResponseDict:
        return await crud_users.get_multi(db=db, offset=skip, limit=limit, schema_to_select=UserRead, is_deleted=False)

    async def get_by_id(self, user_id: int, db: AsyncSession, include_deleted: bool = False) -> dict[str, Any]:
        filters: dict[str, Any] = {} if include_deleted else {"is_deleted": False}
        user: dict[str, Any] | None = await crud_users.get(db=db, schema_to_select=UserRead, id=user_id, **filters)
        if not user:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        return user

    async def get_by_email(self, email: str, db: AsyncSession) -> dict[str, Any]:
        user = await crud_users.get(db=db, schema_to_select=UserRead, email=email, is_deleted=False)
        if not user:
            raise UserNotFoundError(f"User with email '{email}' not found")
        return user

    def verify_self_or_manager(self, requester: dict[str, Any], target_id: int) -> None:
        if requester.get("id") != target_id and not has_permission(requester, Permission.USERS_MANAGE):
            raise PermissionDeniedError("Not allowed on this user")

    async def update(self, user_id: int, values: UserUpdate, db: AsyncSession, context: AuditContext) -> dict[str, Any]:
        existing = await self.get_by_id(user_id, db)
        changes = values.model_dump(exclude_unset=True)

        if "email" in changes and changes["email"] != existing["email"]:
            if await crud_users.exists(db=db, email=changes["email"]):
                raise UserExistsError("Email already registered")

        changed = {key: value for key, value in changes.items() if existing.get(key) != value}
        if not changed:
            return existing

        await crud_users.update(db=db, object=changed, id=user_id, commit=False)
        self.audit.record(
            db,
            context,
            "user.updated",
            record_type="user",
            record_id=user_id,
            old_values={key: existing.get(key) for key in changed},
            new_values=changed,
        )
        await db.commit()
        return await self.get_by_id(user_id, db)

    async def count_active_admins(self, db: AsyncSession) -> int:
        statement = (
            select(func.count())
            .select_from(User)
            .join(Role, Role.id == User.role_id)
            .where(Role.name == RoleName.ADMIN.value, User.is_deleted.is_(False))
        )
        return (await db.execute(statement)).scalar_one()

    async def verify_admin_removal_allowed(self, existing: dict[str, Any], db: AsyncSession) -> None:
        if existing.get("role_name") != RoleName.ADMIN.value:
            return
        if await self.count_active_admins(db) <= 1:
            raise LastAdminError("Cannot remove the last Admin")

    async def delete(self, user_id: int, db: AsyncSession, context: AuditContext) -> None:
        existing = await self.get_by_id(user_id, db)
        await self.verify_admin_removal_allowed(existing, db)

        await crud_users.delete(db=db, id=user_id, commit=False)
        self.audit.record(
            db,
            context,
            "user.deleted",
            record_type="user",
            record_id=user_id,
            old_values={"is_deleted": False},
            new_values={"is_deleted": True},
        )
        await db.commit()

    async def anonymize_user(self, user_id: int, db: AsyncSession, context: AuditContext) -> None:
        existing = await self.get_by_id(user_id, db, include_deleted=True)
        await self.verify_admin_removal_allowed(existing, db)

        anonymized = UserAnonymize(
            name="[DELETED]",
            hashed_password="DELETED_INVALID_HASH",
            profile_image_url="https://deleted.com/deleted.jpg",
            role_id=None,
            email_verified=False,
        )
        await crud_users.update(db=db, object=anonymized, id=user_id, commit=False)
        if not existing.get("is_deleted"):
            await crud_users.delete(db=db, id=user_id, commit=False)
        self.audit.record(
            db,
            context,
            "user.anonymized",
            record_type="user",
            record_id=user_id,
            old_values={"name": existing["name"], "role": existing.get("role_name")},
            new_values={"name": anonymized.name, "role": None},
        )
        await db.commit()

    async def _role_name(self, role_id: int, db: AsyncSession) -> str:
        role = (await db.execute(select(Role.name).where(Role.id == role_id, Role.is_deleted.is_(False)))).scalar_one_or_none()
        if role is None:
            raise RoleNotFoundError(f"Role with ID {role_id} not found")
        return role

    async def change_role(
        self, user_id: int, values: UserRoleUpdate, db: AsyncSession, context: AuditContext
    ) -> dict[str, Any]:
        existing = await self.get_by_id(user_id, db)
        new_role = await self._role_name(values.role_id, db)
        if existing.get("role_id") == values.role_id:
            return existing
        if new_role != RoleName.ADMIN.value:
            await self.verify_admin_removal_allowed(existing, db)

        await crud_users.update(db=db, object={"role_id": values.role_id}, id=user_id, commit=False)
        self.audit.record(
            db,
            context,
            "user.role_changed",
            record_type="user",
            record_id=user_id,
            old_values={"role": existing.get("role_name")},
            new_values={"role": new_role},
        )
        await db.commit()
        return await self.get_by_id(user_id, db)

    async def add_role(self, user_id: int, values: UserRoleUpdate, db: AsyncSession, context: AuditContext) -> dict[str, Any]:
        """Granting a role on top of an existing one is refused: v1 is one role per user."""
        existing = await self.get_by_id(user_id, db)
        if existing.get("role_id") is not None and existing.get("role_name") is not None:
            raise OneRolePerUserError("A user can hold only one role")
        return await self.change_role(user_id, values, db, context)
