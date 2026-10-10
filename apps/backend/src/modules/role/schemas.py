from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from ..common.schemas import TimestampSchema


class RoleBase(BaseModel):
    name: Annotated[
        str,
        Field(
            description="Name of the role",
            examples=["user", "moderator", "admin"],
            min_length=1,
            max_length=50,
        ),
    ]


class Role(TimestampSchema, RoleBase):
    pass


class RoleSelect(BaseModel):
    id: int
    name: str


class RoleRead(RoleBase):
    id: int
    created_at: datetime
    description: str | None = None
    is_deleted: bool = False


class RoleCreate(RoleBase):
    description: Annotated[
        str | None,
        Field(
            description="Description of the role",
            max_length=500,
            default=None,
        ),
    ]


class RoleCreateInternal(RoleCreate):
    pass


class RoleUpdate(BaseModel):
    name: Annotated[
        str | None,
        Field(
            description="Name of the role",
            min_length=1,
            max_length=50,
            default=None,
        ),
    ]
    description: Annotated[
        str | None,
        Field(
            description="Description of the role",
            max_length=500,
            default=None,
        ),
    ]


class RoleUpdateInternal(RoleUpdate):
    updated_at: datetime


class RoleDelete(BaseModel):
    pass
