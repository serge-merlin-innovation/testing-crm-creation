from datetime import UTC, datetime
from typing import Any, cast

from crudauth import get_password_hash
from fastcrud.types import GetMultiResponseDict
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.logging import get_logger
from ..common.exceptions import PermissionDeniedError, RoleNotFoundError, UserExistsError, UserNotFoundError, ValidationError
from ..role.crud import crud_roles
from ..role.models import Role
from ..role.schemas import RoleRead
from .crud import crud_users
from .schemas import (
    User as UserSchema,
)
from .schemas import (
    UserAnonymize,
    UserCreate,
    UserCreateInternal,
    UserRead,
    UserRoleUpdate,
    UserSuperuserUpdate,
    UserUpdate,
)

logger = get_logger()


class UserService:
    async def create(self, user: UserCreate, db: AsyncSession) -> dict[str, Any]:
        email_exists = await crud_users.exists(db=db, email=user.email)
        if email_exists:
            raise UserExistsError("Email already registered")

        username_exists = await crud_users.exists(db=db, username=user.username)
        if username_exists:
            raise UserExistsError("Username already taken")

        user_internal_dict = user.model_dump()
        user_internal_dict["hashed_password"] = get_password_hash(password=user_internal_dict["password"])
        del user_internal_dict["password"]

        user_internal = UserCreateInternal(**user_internal_dict)
        created_user = await crud_users.create(db=db, object=user_internal, schema_to_select=UserRead)
        if not created_user:
            raise UserExistsError("Failed to create user")
        return created_user

    async def get_paginated(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> GetMultiResponseDict:
        if db is None:
            raise ValueError("Database session cannot be None")

        return await crud_users.get_multi(
            db=db,
            offset=skip,
            limit=limit,
            schema_to_select=UserRead,
            is_deleted=False,
        )

    async def get_by_username(self, username: str, db: AsyncSession) -> dict[str, Any]:
        user = await crud_users.get(
            db=db,
            schema_to_select=UserRead,
            username=username,
            is_deleted=False,
        )
        if not user:
            raise UserNotFoundError(f"User with username '{username}' not found")
        return user

    async def get_active_and_inactive_by_username(self, username: str, db: AsyncSession) -> dict[str, Any]:
        user = await crud_users.get(db=db, schema_to_select=UserRead, username=username)
        if not user:
            raise UserNotFoundError(f"User with username '{username}' not found")
        return user

    async def get_by_email(self, email: str, db: AsyncSession) -> dict[str, Any]:
        user = await crud_users.get(
            db=db,
            schema_to_select=UserRead,
            email=email,
            is_deleted=False,
        )
        if not user:
            raise UserNotFoundError(f"User with email '{email}' not found")
        return user

    async def update(self, user_id: int, user_update: UserUpdate, db: AsyncSession) -> dict[str, Any]:
        existing_user = await crud_users.get(db=db, id=user_id, is_deleted=False)
        if not existing_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        update_data = user_update.model_dump(exclude_unset=True)

        if "email" in update_data and update_data["email"] != existing_user["email"]:
            email_exists = await crud_users.exists(db=db, email=update_data["email"])
            if email_exists:
                raise UserExistsError("Email already registered")

        if "username" in update_data and update_data["username"] != existing_user["username"]:
            username_exists = await crud_users.exists(db=db, username=update_data["username"])
            if username_exists:
                raise UserExistsError("Username already taken")

        updated_user = await crud_users.update(
            db=db, object=user_update, id=user_id, return_columns=list(UserSchema.model_fields.keys())
        )
        if not updated_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        return updated_user

    async def check_update_permission(self, requester_user: dict[str, Any], target_username: str) -> bool:
        if requester_user.get("is_superuser", False):
            return True

        return requester_user.get("username") == target_username

    async def verify_user_permission(
        self, requester_user: dict[str, Any], target_username: str, action_description: str = "perform this action"
    ) -> None:
        has_permission = await self.check_update_permission(requester_user, target_username)
        if not has_permission:
            raise PermissionDeniedError(f"You don't have permission to {action_description} on this user")

    async def count_active_superusers(self, db: AsyncSession) -> int:
        return await crud_users.count(db=db, is_superuser=True, is_deleted=False)

    async def verify_superuser_removal_allowed(self, existing_user: dict[str, Any], db: AsyncSession) -> None:
        """Call before permanently or temporarily removing a user's account or superuser status."""
        if not existing_user.get("is_superuser"):
            return
        if await self.count_active_superusers(db) <= 1:
            logger.warning("Blocked action that would remove the workspace's last active superuser")
            raise PermissionDeniedError("Cannot remove the workspace's last superuser")

    async def delete(self, user_id: int, db: AsyncSession) -> None:
        existing_user = await crud_users.get(db=db, id=user_id, is_deleted=False, schema_to_select=UserRead)
        if not existing_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        await self.verify_superuser_removal_allowed(existing_user, db)

        try:
            await crud_users.delete(db=db, id=user_id)
        except NoResultFound:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        except MultipleResultsFound:
            raise ValidationError("Multiple users found with same ID")

    async def permanent_delete(self, user_id: int, db: AsyncSession) -> None:
        try:
            await crud_users.db_delete(db=db, id=user_id)
        except NoResultFound:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        except MultipleResultsFound:
            raise ValidationError("Multiple users found with same ID")

    async def anonymize_user(self, user_id: int, db: AsyncSession) -> None:
        try:
            existing_user = await crud_users.get(db=db, schema_to_select=UserRead, id=user_id)
            if not existing_user:
                raise UserNotFoundError(f"User with ID {user_id} not found")

            await self.verify_superuser_removal_allowed(existing_user, db)

            timestamp = int(datetime.now(UTC).timestamp())

            logger.info(
                "User anonymization requested",
                extra={
                    "user_id": user_id,
                    "email": existing_user.get("email"),
                    "action": "user_anonymization_start",
                },
            )

            anonymize_data = UserAnonymize(
                name="[DELETED]",
                username=f"del_{user_id}_{timestamp % 10000}",
                hashed_password="DELETED_INVALID_HASH",
                profile_image_url="https://deleted.com/deleted.jpg",
                role_id=None,
                is_superuser=False,
                microsoft_id=None,
                oauth_provider=None,
                email_verified=False,
                oauth_created_at=None,
                oauth_updated_at=None,
            )

            await crud_users.update(db=db, object=anonymize_data, commit=False, id=user_id)
            await crud_users.delete(db=db, id=user_id)

            anonymized_fields = list(anonymize_data.model_dump(exclude_unset=True).keys())
            logger.info(
                "User anonymization completed",
                extra={
                    "user_id": user_id,
                    "retained_data": ["email", "created_at", "updated_at", "id"],
                    "anonymized_fields": anonymized_fields,
                    "action": "user_anonymization_complete",
                    "foreign_keys_preserved": True,
                },
            )

        except NoResultFound:
            logger.warning(
                "User anonymization failed - user not found",
                extra={"user_id": user_id, "action": "user_anonymization_failed", "reason": "user_not_found"},
            )
            raise UserNotFoundError(f"User with ID {user_id} not found")

    async def update_role(self, user_id: int, role_update: UserRoleUpdate, db: AsyncSession) -> dict[str, Any]:
        # role_id and is_superuser are independent columns (see Role model docstring) - reassigning
        # a role never changes superuser status, so this method has no last-superuser guard to make.
        existing_user = await crud_users.get(db=db, id=user_id, is_deleted=False)
        if not existing_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        role_exists = await crud_roles.exists(db=db, id=role_update.role_id)
        if not role_exists:
            raise RoleNotFoundError(f"Role with ID {role_update.role_id} not found")

        updated_user = await crud_users.update(
            db=db, object=role_update, id=user_id, return_columns=list(UserSchema.model_fields.keys())
        )
        if not updated_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        return updated_user

    async def update_superuser_status(self, user_id: int, is_superuser: bool, db: AsyncSession) -> dict[str, Any]:
        existing_user = await crud_users.get(db=db, id=user_id, is_deleted=False)
        if not existing_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        if not is_superuser:
            await self.verify_superuser_removal_allowed(existing_user, db)

        updated_user = await crud_users.update(
            db=db,
            object=UserSuperuserUpdate(is_superuser=is_superuser),
            id=user_id,
            return_columns=list(UserSchema.model_fields.keys()),
        )
        if not updated_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        return updated_user

    async def get_user_with_role(self, user_id: int, db: AsyncSession) -> dict[str, Any]:
        user_dict = await crud_users.get(db=db, id=user_id, is_deleted=False, schema_to_select=UserRead)
        if not user_dict:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        # ``role_name`` comes back null both when the user holds no role and when ``role_id`` points
        # at a row that is gone, so it answers on its own what a second existence query used to.
        if user_dict.get("role_name") is None:
            user_dict["role"] = None
            return user_dict

        result = await crud_users.get_joined(
            db=db,
            join_model=Role,
            join_prefix="role_",
            schema_to_select=UserRead,
            join_schema_to_select=RoleRead,
            id=user_id,
            nest_joins=True,
        )

        return cast(dict[str, Any], result)
