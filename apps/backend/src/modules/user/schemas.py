from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..common.schemas import PersistentDeletion, TimestampSchema

PASSWORD_FIELD = Field(
    min_length=8,
    description="At least 8 characters.",
    examples=["Str1ngst!"],
)


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


class UserCreate(UserBase):
    password: Annotated[str, PASSWORD_FIELD]

    model_config = ConfigDict(extra="forbid")


class UserCreateInternal(UserBase):
    hashed_password: str


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=2, max_length=100, default=None)]
    email: Annotated[EmailStr | None, Field(default=None)]
    profile_image_url: Annotated[
        str | None,
        Field(pattern=r"^(https?|ftp)://[^\s/$.?#].[^\s]*$", examples=["https://www.profileimageurl.com"], default=None),
    ]


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
