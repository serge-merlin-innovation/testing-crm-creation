from typing import Annotated, Any

from fastapi import APIRouter, status

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import OperationsServiceDep
from .schemas import (
    DrillCreate,
    DrillRead,
    DrillStatus,
    FindingCreate,
    FindingRead,
    FindingUpdate,
    MaintenanceCreate,
    MaintenanceRead,
    ReleaseGate,
)

router = APIRouter(tags=["Operations"])

OperatorDep = Annotated[dict[str, Any], require_permission(Permission.SETTINGS_MANAGE)]


@router.post(
    "/recovery-drills",
    response_model=DrillRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log a restore test or disaster-recovery run; passes when RPO <= 24 h and RTO <= 8 h",
)
async def log_drill(
    values: DrillCreate, db: AsyncSessionDep, service: OperationsServiceDep, context: AuditContextDep, user: OperatorDep
) -> dict[str, Any]:
    return await service.log_drill(db, user, values, context)


@router.get("/recovery-drills", response_model=list[DrillRead], summary="Logged recovery drills, newest first")
async def list_drills(db: AsyncSessionDep, service: OperationsServiceDep, _: OperatorDep) -> list[dict[str, Any]]:
    return await service.drills(db)


@router.get("/recovery-drills/status", response_model=DrillStatus, summary="Whether this quarter's restore test is due")
async def drill_status(db: AsyncSessionDep, service: OperationsServiceDep, clock: ClockDep, _: OperatorDep) -> dict[str, Any]:
    return await service.drill_status(db, clock.now())


@router.post(
    "/security-findings",
    response_model=FindingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a penetration-test or scanner finding; high and critical are due in 30 days",
)
async def add_finding(
    values: FindingCreate, db: AsyncSessionDep, service: OperationsServiceDep, context: AuditContextDep, user: OperatorDep
) -> dict[str, Any]:
    return await service.add_finding(db, user, values, context)


@router.get("/security-findings", response_model=list[FindingRead], summary="Security findings, newest first")
async def list_findings(db: AsyncSessionDep, service: OperationsServiceDep, _: OperatorDep) -> list[dict[str, Any]]:
    return await service.findings(db)


@router.patch("/security-findings/{finding_id}", response_model=FindingRead, summary="Mark a finding fixed, accepted or open")
async def update_finding(
    finding_id: int,
    values: FindingUpdate,
    db: AsyncSessionDep,
    service: OperationsServiceDep,
    context: AuditContextDep,
    _: OperatorDep,
) -> dict[str, Any]:
    return await service.update_finding(db, finding_id, values.status, context)


@router.get(
    "/release-gate",
    response_model=ReleaseGate,
    summary="Releasable only with no open high or critical finding (NFR-01 c3)",
)
async def release_gate(db: AsyncSessionDep, service: OperationsServiceDep, clock: ClockDep, _: OperatorDep) -> dict[str, Any]:
    return await service.release_gate(db, clock.now())


@router.post(
    "/maintenance-windows",
    response_model=MaintenanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Announce planned maintenance to every user; at least 48 h ahead and outside business hours",
)
async def announce_maintenance(
    values: MaintenanceCreate, db: AsyncSessionDep, service: OperationsServiceDep, context: AuditContextDep, user: OperatorDep
) -> dict[str, Any]:
    return await service.announce(db, user, values, context)


@router.get("/maintenance-windows/upcoming", response_model=list[MaintenanceRead], summary="Planned maintenance not yet over")
async def upcoming_maintenance(
    db: AsyncSessionDep, service: OperationsServiceDep, clock: ClockDep, _: CurrentUserDep
) -> list[Any]:
    return await service.upcoming(db, clock.now())
