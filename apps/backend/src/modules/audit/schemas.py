from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntryRead(BaseModel):
    id: int
    action: str
    created_at: datetime
    retain_until: datetime
    user_id: int | None = None
    record_type: str | None = None
    record_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None

