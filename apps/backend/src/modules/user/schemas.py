from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..common.schemas import PersistentDeletion, TimestampSchema


class UserBase(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=100, examples=["Ann Peeters"])]
    email: Annotated[EmailStr, Field(examples=["ann.peeters@firm.be"])]


class User(TimestampSchema, UserBase, PersistentDeletion):
    hashed_password: str
    profile_image_url: Annotated[str, Field(default="https://www.profileimageurl.com")]
    role_id: int | None = None
    email_verified: bool = False


class UserRead(BaseModel):
    """Sent to clients as well as used for internal selects, so it must never carry a secret."""

    id: int
    name: str
    email: EmailStr
    profile_image_url: str
    is_deleted: bool = False
    role_id: int | None
    # Read-only, resolved by the model's mapped expressions.
    role_name: str | None = None
    permissions: list[str] | None = None
    email_verified: bool = False
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    status: str = "active"
    language: str = "en"


class UserCreate(BaseModel):
    """An admin creates the account as Invited; the person sets their own password from the invitation."""

    model_config = ConfigDict(extra="forbid")

    first_name: Annotated[str, Field(min_length=1, max_length=50, examples=["Ann"])]
    last_name: Annotated[str, Field(min_length=1, max_length=50, examples=["Peeters"])]
    email: Annotated[EmailStr, Field(examples=["ann.peeters@firm.be"])]
    title: Annotated[str | None, Field(max_length=100, examples=["Associate"])] = None
    role_id: int


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=2, max_length=100, default=None)]
    email: Annotated[EmailStr | None, Field(default=None)]
    profile_image_url: Annotated[
        str | None,
        Field(pattern=r"^(https?|ftp)://[^\s/$.?#].[^\s]*$", examples=["https://www.profileimageurl.com"], default=None),
    ]
    language: Literal["en", "fr", "nl"] | None = None


class UserUpdateInternal(UserUpdate):
    updated_at: datetime


class UserRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: int


class UserDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_deleted: bool
    deleted_at: datetime


class UserAnonymize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    hashed_password: str | None = None
    profile_image_url: str | None = None
    role_id: int | None = None
    email_verified: bool = False


class UserRestoreDeleted(BaseModel):
    is_deleted: bool
