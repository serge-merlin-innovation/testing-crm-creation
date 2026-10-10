from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class InvitationRead(BaseModel):
    email: EmailStr
    first_name: str | None
    last_name: str | None


class SetPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=256)


class ForgotPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)


class ChangePassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class PasswordPolicyRead(BaseModel):
    min_length: int
    history_count: int


class PasswordPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_length: int | None = Field(default=None, ge=12, le=128)
    history_count: int | None = Field(default=None, ge=5, le=24)


class ImportRow(BaseModel):
    line: int
    email: str
    status: Literal["created", "error"]
    id: int | None = None
    field: str | None = None
    message: str | None = None


class ImportResult(BaseModel):
    rows: list[ImportRow]


class UserListRow(BaseModel):
    id: int
    name: str
    first_name: str | None
    last_name: str | None
    email: EmailStr
    title: str | None
    role_id: int | None
    role_name: str | None
    status: str
    invited_at: datetime | None
    last_login_at: datetime | None
    dormant: bool
    can_resend_invitation: bool


class UserList(BaseModel):
    data: list[UserListRow]
    total_count: int
    has_more: bool
    page: int
    items_per_page: int
