from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OwnedRecord(BaseModel):
    type: str
    id: int
    label: str


class OffboardingPreview(BaseModel):
    user_id: int
    name: str
    contacts: list[OwnedRecord]
    tasks: list[OwnedRecord]
    deals: list[OwnedRecord]
    deal_memberships: int
    needs_new_owner: bool
    # Deals need a lead partner, so the new owner must hold the Partner role when deals are listed.
    new_owner_must_be_partner: bool


class DeactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_owner_id: int | None = None


class OffboardingConfirmation(BaseModel):
    user_id: int
    at: datetime
    sessions_ended: int
    api_tokens_revoked: int
    api_clients_revoked: int
    deal_memberships_removed: int
    new_owner_id: int | None
    new_owner_name: str | None
    reassigned: list[OwnedRecord]


class Reactivated(BaseModel):
    user_id: int
    role_name: str | None
    deal_memberships: int
