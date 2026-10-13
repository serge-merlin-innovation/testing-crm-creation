from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DrillKind(StrEnum):
    RESTORE_TEST = "restore_test"
    DISASTER_RECOVERY = "disaster_recovery"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingSource(StrEnum):
    PENTEST = "pentest"
    ZAP = "zap"
    OTHER = "other"


class FindingStatus(StrEnum):
    OPEN = "open"
    FIXED = "fixed"
    ACCEPTED = "accepted"


class DrillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: DrillKind
    backup_taken_at: AwareDatetime
    started_at: AwareDatetime
    service_restored_at: AwareDatetime
    data_verified: bool
    notes: Annotated[str, Field(max_length=2000)] = ""


class DrillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: DrillKind
    backup_taken_at: datetime
    started_at: datetime
    service_restored_at: datetime
    data_verified: bool
    data_loss_hours: float
    recovery_hours: float
    passed: bool
    failures: list[str]
    logged_at: datetime
    notes: str


class DrillStatus(BaseModel):
    restore_test_due: bool
    last_passed_at: datetime | None
    rpo_hours: int
    rto_hours: int


class FindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: FindingSource
    severity: Severity
    title: Annotated[str, Field(min_length=1, max_length=300)]
    reference: Annotated[str, Field(max_length=100)] = ""
    reported_at: AwareDatetime | None = None


class FindingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FindingStatus


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: FindingSource
    severity: Severity
    title: str
    reference: str
    status: FindingStatus
    reported_at: datetime
    due_at: datetime | None
    fixed_at: datetime | None
    fixed_in_time: bool | None


class ReleaseGate(BaseModel):
    releasable: bool
    open_blocking: int
    overdue: int


class MaintenanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: AwareDatetime
    ends_at: AwareDatetime
    reason: Annotated[str, Field(min_length=1, max_length=300)]


class MaintenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    starts_at: datetime
    ends_at: datetime
    reason: str
    announced_at: datetime
