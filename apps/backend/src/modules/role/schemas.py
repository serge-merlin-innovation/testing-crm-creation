from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from .permissions import ALL_PERMISSIONS


class RoleRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    created_at: datetime
    is_deleted: bool = False


class RolePermissionsUpdate(BaseModel):
    permissions: Annotated[list[str], Field(examples=[["audit.read", "users.manage"]])]

    @field_validator("permissions")
    @classmethod
    def known_permissions_only(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(ALL_PERMISSIONS))
        if unknown:
            raise ValueError(f"Unknown permissions: {unknown}")
        return sorted(set(value))


class MatrixColumn(BaseModel):
    id: int
    name: str


class MatrixRow(BaseModel):
    permission: str
    granted: list[bool]


class PermissionMatrix(BaseModel):
    columns: list[MatrixColumn]
    rows: list[MatrixRow]
