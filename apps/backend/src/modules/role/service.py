from typing import Any

from fastcrud.types import GetMultiResponseDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import PermissionDeniedError, ResourceExistsError, RoleNotFoundError
from .crud import crud_roles
from .schemas import (
    RoleCreate,
    RoleCreateInternal,
    RoleRead,
    RoleUpdate,
)


class RoleService:
    async def create(self, role: RoleCreate, db: AsyncSession) -> dict[str, Any]:
        role_dict = role.model_dump()
        if await crud_roles.exists(db=db, name=role_dict["name"]):
            raise ResourceExistsError(f"Role with name '{role_dict['name']}' already exists")

        role_internal = RoleCreateInternal(**role_dict)
        created_role = await crud_roles.create(db=db, object=role_internal, schema_to_select=RoleRead)
        if not created_role:
            raise ResourceExistsError("Failed to create role")
        return created_role

    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> GetMultiResponseDict:
        return await crud_roles.get_multi(db=db, offset=skip, limit=limit, schema_to_select=RoleRead, is_deleted=False)

    async def get_by_id(self, role_id: int, db: AsyncSession) -> dict[str, Any]:
        role = await crud_roles.get(db=db, id=role_id, schema_to_select=RoleRead, is_deleted=False)
        if not role:
            raise RoleNotFoundError(f"Role with ID {role_id} not found")
        return role

    async def get_by_name(self, name: str, db: AsyncSession) -> dict[str, Any]:
        role = await crud_roles.get(db=db, name=name, schema_to_select=RoleRead, is_deleted=False)
        if not role:
            raise RoleNotFoundError(f"Role with name '{name}' not found")
        return role

    async def update(self, name: str, role_update: RoleUpdate, db: AsyncSession) -> None:
        existing_role = await crud_roles.get(db=db, name=name, schema_to_select=RoleRead)
        if not existing_role:
            raise RoleNotFoundError(f"Role with name '{name}' not found")

        update_data = role_update.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"] != name:
            if await crud_roles.exists(db=db, name=update_data["name"]):
                raise ResourceExistsError(f"Role with name '{update_data['name']}' already exists")

        await crud_roles.update(db=db, object=role_update, name=name)

    async def delete(self, name: str, db: AsyncSession) -> None:
        existing_role = await crud_roles.get(db=db, name=name, schema_to_select=RoleRead, is_deleted=False)
        if not existing_role:
            raise RoleNotFoundError(f"Role with name '{name}' not found")
        await crud_roles.delete(db=db, name=name)

    async def permanent_delete(self, name: str, db: AsyncSession) -> None:
        existing_role = await crud_roles.get(db=db, name=name, schema_to_select=RoleRead)
        if not existing_role:
            raise RoleNotFoundError(f"Role with name '{name}' not found")
        await crud_roles.db_delete(db=db, name=name)

    async def verify_superuser(self, user: dict[str, Any], action: str = "manage roles") -> None:
        if not user.get("is_superuser", False):
            raise PermissionDeniedError(f"Only superusers can {action}")
