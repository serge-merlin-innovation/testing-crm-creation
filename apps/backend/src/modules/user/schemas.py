from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..common.schemas import PersistentDeletion, TimestampSchema


class UserBase(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=30, examples=["User Userson"])]
    username: Annotated[
        str,
        Field(min_length=2, max_length=20, pattern=r"^[a-z0-9]+$", examples=["userson"]),
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]


class User(TimestampSchema, UserBase, PersistentDeletion):
    hashed_password: str
    is_superuser: bool = False
    profile_image_url: Annotated[
        str,
        Field(
            default="https://www.profileimageurl.com",
            description="URL of the user's profile image",
        ),
    ]
    role_id: int | None = None

    microsoft_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserRead(BaseModel):
    """Sent to clients as well as used for internal selects, so it must never carry a secret."""

    id: int
    name: Annotated[str, Field(min_length=2, max_length=30, examples=["User Userson"])]
    username: Annotated[
        str,
        Field(min_length=2, max_length=20, pattern=r"^[a-z0-9]+$", examples=["userson"]),
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]
    profile_image_url: str
    is_deleted: bool = False
    role_id: int | None
    # Read-only, resolved by the model's mapped expression. Defaulted because the hand-built dicts
    # the dependency-override test clients return do not carry it.
    role_name: str | None = None
    is_superuser: bool = False
    email_verified: bool = False
    oauth_provider: str | None = None


class UserCreate(UserBase):
    password: Annotated[
        str,
        Field(
            min_length=8,
            description=(
                "Password must be at least 8 characters long and include a number,"
                "uppercase letter, lowercase letter, and special character"
            ),
            examples=["Str1ngst!"],
            pattern=r"^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$",
        ),
    ]
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class UserCreateInternal(UserBase):
    hashed_password: str
    # Deliberately absent from UserCreate and UserUpdate: those are client-supplied
    # bodies (POST /users is unauthenticated, PATCH /users/{username} is self-service),
    # so exposing microsoft_id there would let anyone claim an arbitrary Entra object
    # id. It is set directly on the user record, never through the API.
    microsoft_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str | None,
        Field(min_length=2, max_length=30, examples=["User Userberg"], default=None),
    ]
    username: Annotated[
        str | None,
        Field(
            min_length=2,
            max_length=20,
            pattern=r"^[a-z0-9]+$",
            examples=["userberg"],
            default=None,
        ),
    ]
    email: Annotated[EmailStr | None, Field(examples=["user.userberg@example.com"], default=None)]
    profile_image_url: Annotated[
        str | None,
        Field(
            pattern=r"^(https?|ftp)://[^\s/$.?#].[^\s]*$",
            examples=["https://www.profileimageurl.com"],
            default=None,
        ),
    ]
    oauth_provider: str | None = None
    email_verified: bool | None = None
    oauth_updated_at: datetime | None = None


class UserUpdateInternal(UserUpdate):
    updated_at: datetime


class UserRoleUpdate(BaseModel):
    role_id: int


class UserSuperuserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_superuser: bool


class UserDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_deleted: bool
    deleted_at: datetime


class UserAnonymize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    username: str
    hashed_password: str | None = None
    profile_image_url: str | None = None
    role_id: int | None = None
    is_superuser: bool = False
    microsoft_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserRestoreDeleted(BaseModel):
    is_deleted: bool
