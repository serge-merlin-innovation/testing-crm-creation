from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..common.exceptions import ValidationError
from ..mandate.policy import EditGrant, ReadGrant
from ..role.authorization import RequireRecordAccess, require_permission
from ..role.permissions import Permission
from .dependencies import ReportingServiceDep
from .schemas import DashboardRead, FeeForecastRead, ForecastRead, ForecastValues, HomeRead, WinLossRead

router = APIRouter(tags=["Reports"])
deal_router = APIRouter(tags=["Reports"])


DashboardDep = Annotated[dict[str, Any], require_permission(Permission.DASHBOARD_AGGREGATED)]
FirmDep = Annotated[dict[str, Any], require_permission(Permission.DASHBOARD_FIRM)]
FeeReaderDep = Annotated[dict[str, Any], require_permission(Permission.FEES_READ)]
HIDDEN: dict[int | str, dict[str, Any]] = {404: {"description": "Not found, or a deal you may not read"}}


@router.get(
    "/home",
    response_model=HomeRead,
    summary="My home page: my active deals by stage, tasks due this week, key dates in the next 30 days",
    dependencies=[RequireRecordAccess],
)
async def home(db: AsyncSessionDep, service: ReportingServiceDep, user: CurrentUserDep, clock: ClockDep) -> dict[str, Any]:
    return await service.home(db, user, clock.now())


@router.get(
    "/dashboard",
    response_model=DashboardRead,
    response_model_exclude_unset=True,
    summary="Firm pipeline: mandates by stage and type, weighted expected fees by quarter",
    description=(
        "Counts running deals firm-wide. Deals the caller is not staffed on count only inside a cell with at "
        "least 3 of them, so no figure reveals one deal. Fee figures need `fees.read`."
    ),
)
async def dashboard(db: AsyncSessionDep, service: ReportingServiceDep, user: DashboardDep, clock: ClockDep) -> dict[str, Any]:
    return await service.dashboard(db, user, clock.now())


@router.get(
    "/fee-forecast",
    response_model=FeeForecastRead,
    summary="Retainers and success fees per month for 12 months, with invoiced and paid actuals (fees.read)",
    dependencies=[RequireRecordAccess],
)
async def fee_forecast(
    db: AsyncSessionDep, service: ReportingServiceDep, user: FeeReaderDep, clock: ClockDep
) -> dict[str, Any]:
    return await service.fee_forecast(db, user, clock.now())


@router.get(
    "/fee-forecast/export",
    summary="The fee forecast as an Excel workbook (fees.read); the export is audited",
    response_class=Response,
    dependencies=[RequireRecordAccess],
)
async def fee_forecast_export(
    db: AsyncSessionDep, service: ReportingServiceDep, user: FeeReaderDep, clock: ClockDep, context: AuditContextDep
) -> Response:
    body = service.fee_forecast_xlsx(db, await service.fee_forecast(db, user, clock.now()), context)
    await db.commit()
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="fee-forecast.xlsx"'},
    )


@router.get(
    "/win-loss",
    response_model=WinLossRead,
    summary="Pitches, win rate, top lost reasons, deal duration and EV/EBITDA by sector for a period (Partner)",
    description="Counts only opportunities and deals the caller may read.",
)
async def win_loss(
    db: AsyncSessionDep,
    service: ReportingServiceDep,
    user: FirmDep,
    clock: ClockDep,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> dict[str, Any]:
    if end < start:
        raise ValidationError("The period ends before it starts", field="to")
    return await service.win_loss(db, user, clock.now(), start, end)


@deal_router.get("/{mandate_id}/forecast", response_model=ForecastRead, summary="Close probability and date", responses=HIDDEN)
async def get_forecast(grant: ReadGrant, db: AsyncSessionDep, service: ReportingServiceDep) -> dict[str, Any]:
    return await service.read_forecast(db, grant)


@deal_router.put(
    "/{mandate_id}/forecast",
    response_model=ForecastRead,
    summary="Set the close probability and expected closing date (deal team)",
    responses=HIDDEN,
)
async def put_forecast(
    values: ForecastValues, grant: EditGrant, db: AsyncSessionDep, service: ReportingServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.save_forecast(db, grant, values, context)
