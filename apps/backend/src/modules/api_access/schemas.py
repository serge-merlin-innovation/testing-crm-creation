from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Power BI export"}]})

    name: str = Field(min_length=1, max_length=100)


class ApiTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    created_at: datetime
    revoked_at: datetime | None


class ApiTokenIssued(ApiTokenRead):
    token: str = Field(description="Shown once. Send it as `Authorization: Bearer <token>`.")


class ApiClientCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Virtual data room"}]})

    name: str = Field(min_length=1, max_length=100)


class ApiClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    client_id: str
    created_at: datetime
    revoked_at: datetime | None


class ApiClientIssued(ApiClientRead):
    client_secret: str = Field(description="Shown once. Exchange it at POST /api/v1/oauth/token.")


class OAuthToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class OAuthError(BaseModel):
    error: str
    error_description: str | None = None
