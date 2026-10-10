"""Home page, firm dashboard, fee forecast and win/loss report (REP-01..04).

The wall (AUTHZ-02 c4): a deal the viewer cannot read never appears by id, code name, client or
fee in any payload here. The firm dashboard counts such deals only in its firm-wide totals, and only
once there are at least HIDDEN_CELL_MINIMUM of them: no stage, type or quarter cell ever holds one,
so comparing dashboards over time cannot show a hidden deal moving between cells.
"""

import io
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from openpyxl import Workbook  # type: ignore[import-untyped]
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.money import to_cents
from ..common.spreadsheet import safe_row
from ..fee.models import FeeTerms, Invoice
from ..fee.schemas import FeeTermsValues, InvoiceType, LehmanTier, SuccessFeeKind
from ..fee.service import net_fee
from ..mandate.models import DealTeamMember, Mandate, Milestone
from ..mandate.pipeline import CLOSED_STAGES
from ..mandate.policy import DealGrant, DealPolicy, in_conflict_hiding
from ..mandate.stages import DealStage
from ..origination.models import Opportunity
from ..origination.schemas import OpportunityStage
from ..origination.service import visible as visible_opportunities
from ..picklist.models import PicklistValue
from ..role.authorization import has_permission
from ..role.permissions import Permission
from ..task.models import Task
from ..task.service import read as read_task
from .models import DealForecast
from .schemas import ForecastValues

HIDDEN_CELL_MINIMUM = 3
KEY_DATE_HORIZON = timedelta(days=30)
FORECAST_MONTHS = 12
TOP_LOST_REASONS = 3

# Default close probability per stage, used until the team sets its own on the deal.
STAGE_PROBABILITY: dict[str, int] = {
    DealStage.CONFLICT_REVIEW: 5,
    DealStage.PREPARATION: 10,
    DealStage.MARKETING: 20,
    DealStage.INFORMATION_MEMORANDUM: 25,
    DealStage.INDICATIVE_OFFERS: 35,
    DealStage.DUE_DILIGENCE: 50,
    DealStage.BINDING_OFFERS: 65,
    DealStage.SPA_NEGOTIATION: 80,
    DealStage.SIGNING: 90,
    DealStage.CLOSING: 95,
    DealStage.CLOSED_WON: 100,
    DealStage.ABORTED: 0,
}


def quarter_of(day: date | None) -> str:
    return "unscheduled" if day is None else f"{day.year}-Q{(day.month - 1) // 3 + 1}"


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def months_from(start: date, count: int) -> list[date]:
    months, year, month = [], start.year, start.month
    for _ in range(count):
        months.append(date(year, month, 1))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def week_of(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def terms_values(row: FeeTerms) -> FeeTermsValues:
    return FeeTermsValues(
        retainer_monthly=row.retainer_monthly,
        success_fee_kind=SuccessFeeKind(row.success_fee_kind),
        success_fee_percent=row.success_fee_percent,
        success_fee_fixed=row.success_fee_fixed,
        minimum_fee=row.minimum_fee,
        lehman_tiers=[LehmanTier.model_validate(tier) for tier in row.lehman_tiers],
        retainers_creditable=row.retainers_creditable,
    )


@dataclass
class _Deal:
    mandate: Mandate
    probability: int
    closing: date | None
    expected_fee: Decimal
    terms: FeeTerms | None


class ReportingService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    # Per-deal forecast inputs

    async def _forecast_row(self, db: AsyncSession, mandate_id: int) -> DealForecast | None:
        return (await db.execute(select(DealForecast).where(DealForecast.mandate_id == mandate_id))).scalar_one_or_none()

    @staticmethod
    def _forecast_read(mandate: Mandate, row: DealForecast | None) -> dict[str, Any]:
        own = row.probability if row else None
        return {
            "mandate_id": mandate.id,
            "probability": own if own is not None else STAGE_PROBABILITY[mandate.stage],
            "probability_is_default": own is None,
            "expected_closing_date": row.expected_closing_date if row else None,
        }

    async def read_forecast(self, db: AsyncSession, grant: DealGrant) -> dict[str, Any]:
        return self._forecast_read(grant.mandate, await self._forecast_row(db, grant.mandate.id))

    async def save_forecast(
        self, db: AsyncSession, grant: DealGrant, values: ForecastValues, context: AuditContext
    ) -> dict[str, Any]:
        row = await self._forecast_row(db, grant.mandate.id)
        old = self._forecast_read(grant.mandate, row)
        if row is None:
            row = DealForecast(mandate_id=grant.mandate.id, updated_by=grant.user["id"], updated_at=context.clock.now())
            db.add(row)
        row.probability = values.probability
        row.expected_closing_date = values.expected_closing_date
        row.updated_by = grant.user["id"]
        row.updated_at = context.clock.now()
        new = self._forecast_read(grant.mandate, row)
        self.audit.record(
            db,
            context,
            "forecast.set",
            record_type="mandate",
            record_id=grant.mandate.id,
            old_values={key: str(value) if value is not None else None for key, value in old.items()},
            new_values={key: str(value) if value is not None else None for key, value in new.items()},
        )
        await db.commit()
        return new

    async def _deals(self, db: AsyncSession, query: Any) -> list[_Deal]:
        rows = (
            await db.execute(
                query.add_columns(DealForecast, FeeTerms)
                .outerjoin(DealForecast, DealForecast.mandate_id == Mandate.id)
                .outerjoin(FeeTerms, FeeTerms.mandate_id == Mandate.id)
            )
        ).all()
        deals = []
        for mandate, forecast, terms in rows:
            read = self._forecast_read(mandate, forecast)
            paid = Decimal("0")
            if terms is not None and terms.retainers_creditable:
                paid = await _retainers_paid(db, mandate.id)
            fee = net_fee(terms_values(terms), mandate.estimated_ev, paid) if terms is not None else Decimal("0")
            deals.append(_Deal(mandate, read["probability"], read["expected_closing_date"], fee, terms))
        return deals

    # REP-01: home page

    async def home(self, db: AsyncSession, user: dict[str, Any], now: datetime) -> dict[str, Any]:
        today = now.date()
        week_start, week_end = week_of(today)
        policy = DealPolicy(now)
        staffed = select(DealTeamMember.mandate_id).where(
            DealTeamMember.user_id == user["id"],
            or_none_expiry(DealTeamMember.expires_at, now),
        )
        mine = policy.visible(
            user,
            select(Mandate).where(
                Mandate.id.in_(staffed), Mandate.closed_at.is_(None), Mandate.stage.not_in([s.value for s in CLOSED_STAGES])
            ),
        ).order_by(Mandate.code_name)
        deals = list((await db.execute(mine)).scalars())
        by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for mandate in deals:
            by_stage[mandate.stage].append({"id": mandate.id, "code_name": mandate.code_name, "stage": mandate.stage})
        stages = [{"stage": stage, "deals": by_stage[stage]} for stage in DealStage if by_stage.get(stage)]

        visible = await policy.visible_mandate_ids(db, user)
        tasks_query = (
            select(Task)
            .where(
                Task.assignee_id == user["id"],
                Task.completed_at.is_(None),
                Task.due_date <= week_end,
                (Task.mandate_id.is_(None)) | (Task.mandate_id.in_(visible)),
            )
            .order_by(Task.due_date, Task.id)
        )
        tasks = [read_task(task, today) for task in (await db.execute(tasks_query)).scalars()]

        ids = [mandate.id for mandate in deals]
        codes = {mandate.id: mandate.code_name for mandate in deals}
        key_dates: list[dict[str, Any]] = []
        if ids:
            milestones = await db.execute(
                select(Milestone)
                .where(
                    Milestone.mandate_id.in_(ids),
                    Milestone.actual_date.is_(None),
                    Milestone.planned_date >= today,
                    Milestone.planned_date <= today + KEY_DATE_HORIZON,
                )
                .order_by(Milestone.planned_date, Milestone.id)
            )
            key_dates = [
                {"mandate_id": m.mandate_id, "code_name": codes[m.mandate_id], "name": m.name, "planned_date": m.planned_date}
                for m in milestones.scalars()
            ]
            closings = await db.execute(
                select(DealForecast).where(
                    DealForecast.mandate_id.in_(ids),
                    DealForecast.expected_closing_date >= today,
                    DealForecast.expected_closing_date <= today + KEY_DATE_HORIZON,
                )
            )
            key_dates += [
                {
                    "mandate_id": f.mandate_id,
                    "code_name": codes[f.mandate_id],
                    "name": "Expected closing",
                    "planned_date": f.expected_closing_date,
                }
                for f in closings.scalars()
            ]
            key_dates.sort(key=lambda row: (row["planned_date"], row["code_name"]))
        return {
            "deals_by_stage": stages,
            "tasks_due_this_week": tasks,
            "key_dates": key_dates,
            "week_start": week_start,
            "week_end": week_end,
            "is_new": not deals and not tasks,
        }

    # REP-02: firm dashboard

    async def dashboard(self, db: AsyncSession, user: dict[str, Any], now: datetime) -> dict[str, Any]:
        visible = set(await DealPolicy(now).visible_mandate_ids(db, user))
        # Every running deal of the firm, conflict-hidden ones only when the viewer reads them.
        firm = select(Mandate).where(Mandate.closed_at.is_(None)).where(~in_conflict_hiding() | Mandate.id.in_(visible or [-1]))
        deals = await self._deals(db, firm)

        cells: dict[tuple[str, str], list[_Deal]] = defaultdict(list)
        for deal in deals:
            cells[(deal.mandate.stage, deal.mandate.type)].append(deal)
        seen = [deal for deal in deals if deal.mandate.id in visible]
        hidden = _anonymous([deal for deal in deals if deal.mandate.id not in visible])
        by_stage_and_type = []
        for stage in DealStage:
            for (cell_stage, cell_type), members in sorted(cells.items()):
                if cell_stage != stage:
                    continue
                shown = [deal for deal in members if deal.mandate.id in visible]
                if shown:
                    by_stage_and_type.append({"stage": stage, "type": cell_type, "count": len(shown)})
        result: dict[str, Any] = {"total_mandates": len(seen) + len(hidden), "by_stage_and_type": by_stage_and_type}

        if has_permission(user, Permission.FEES_READ):
            quarters: dict[str, list[_Deal]] = defaultdict(list)
            for deal in seen:
                if deal.terms is not None:
                    quarters[quarter_of(deal.closing)].append(deal)
            fees = []
            for quarter in sorted(quarters, key=lambda q: (q == "unscheduled", q)):
                shown = quarters[quarter]
                if shown:
                    fees.append(
                        {
                            "quarter": quarter,
                            "deals": len(shown),
                            "expected_fees": to_cents(sum((d.expected_fee for d in shown), Decimal("0"))),
                            "weighted_fees": to_cents(sum((d.expected_fee * d.probability / 100 for d in shown), Decimal("0"))),
                        }
                    )
            result["weighted_fees_by_quarter"] = fees
            hidden_fees = _anonymous([deal for deal in hidden if deal.terms is not None])
            result["other_teams_weighted_fees"] = (
                to_cents(sum((d.expected_fee * d.probability / 100 for d in hidden_fees), Decimal("0")))
                if hidden_fees
                else None
            )
        return result

    # REP-03: fee forecast

    def _fee_scope(self, user: dict[str, Any], now: datetime, query: Any) -> Any:
        # Back-office reads every deal's fees (ROLE-01 c4, REP-03); everyone else only the deals they read.
        if has_permission(user, Permission.DEALS_READ_SUMMARY):
            return query.where(~in_conflict_hiding())
        return DealPolicy(now).visible(user, query)

    async def fee_forecast(self, db: AsyncSession, user: dict[str, Any], now: datetime) -> dict[str, Any]:
        months = months_from(now.date(), FORECAST_MONTHS)
        keys = [month_key(month) for month in months]
        table = {
            key: {"retainers": Decimal("0"), "success_fees": Decimal("0"), "invoiced": Decimal("0"), "paid": Decimal("0")}
            for key in keys
        }

        scoped = self._fee_scope(user, now, select(Mandate).join(FeeTerms, FeeTerms.mandate_id == Mandate.id))
        mandate_ids = list((await db.execute(scoped.with_only_columns(Mandate.id))).scalars())
        open_deals = await self._deals(db, self._fee_scope(user, now, select(Mandate).where(Mandate.closed_at.is_(None))))
        open_deals = [deal for deal in open_deals if deal.terms is not None]
        for deal in open_deals:
            assert deal.terms is not None
            last = month_key(deal.closing) if deal.closing else keys[-1]
            for key in keys:
                if key <= last:
                    table[key]["retainers"] += deal.terms.retainer_monthly
            if deal.closing and month_key(deal.closing) in table:
                table[month_key(deal.closing)]["success_fees"] += deal.expected_fee * deal.probability / 100

        if mandate_ids:
            invoices = (await db.execute(select(Invoice).where(Invoice.mandate_id.in_(mandate_ids)))).scalars()
            for invoice in invoices:
                sent = month_key(invoice.sent_date)
                if sent in table:
                    table[sent]["invoiced"] += invoice.amount
                if invoice.paid_date and month_key(invoice.paid_date) in table:
                    table[month_key(invoice.paid_date)]["paid"] += invoice.amount
        rows = []
        for key in keys:
            cell = table[key]
            rows.append(
                {
                    "month": key,
                    "retainers": to_cents(cell["retainers"]),
                    "success_fees": to_cents(cell["success_fees"]),
                    "forecast_total": to_cents(cell["retainers"] + cell["success_fees"]),
                    "actual_invoiced": to_cents(cell["invoiced"]),
                    "actual_paid": to_cents(cell["paid"]),
                }
            )
        return {"months": rows, "deals": len(set(mandate_ids) | {d.mandate.id for d in open_deals})}

    def fee_forecast_xlsx(self, db: AsyncSession, forecast: dict[str, Any], context: AuditContext) -> bytes:
        book = Workbook()
        sheet = book.active
        assert sheet is not None
        sheet.title = "Fee forecast"
        sheet.append(
            safe_row(["Month", "Retainers (EUR)", "Success fees (EUR)", "Forecast (EUR)", "Invoiced (EUR)", "Paid (EUR)"])
        )
        for row in forecast["months"]:
            sheet.append(
                safe_row(
                    [
                        row["month"],
                        float(row["retainers"]),
                        float(row["success_fees"]),
                        float(row["forecast_total"]),
                        float(row["actual_invoiced"]),
                        float(row["actual_paid"]),
                    ]
                )
            )
        self.audit.record(
            db, context, "export", record_type="fee_terms", new_values={"kind": "fee_forecast", "rows": len(forecast["months"])}
        )
        out = io.BytesIO()
        book.save(out)
        return out.getvalue()

    # REP-04: win/loss

    async def win_loss(self, db: AsyncSession, user: dict[str, Any], now: datetime, start: date, end: date) -> dict[str, Any]:
        begin = datetime.combine(start, datetime.min.time(), tzinfo=now.tzinfo)
        finish = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=now.tzinfo)
        decided = (
            (
                await db.execute(
                    select(Opportunity).where(
                        visible_opportunities(user),
                        Opportunity.stage.in_([OpportunityStage.WON.value, OpportunityStage.LOST.value]),
                        Opportunity.stage_changed_at >= begin,
                        Opportunity.stage_changed_at < finish,
                    )
                )
            )
            .scalars()
            .all()
        )
        won = sum(1 for o in decided if o.stage == OpportunityStage.WON.value)
        lost = [o for o in decided if o.stage == OpportunityStage.LOST.value]
        reasons = Counter(o.lost_reason or "unspecified" for o in lost)
        top = sorted(reasons.items(), key=lambda item: (-item[1], item[0]))[:TOP_LOST_REASONS]

        closed = (
            await db.execute(
                DealPolicy(now).visible(
                    user,
                    select(Mandate, PicklistValue.label_en)
                    .join(PicklistValue, PicklistValue.id == Mandate.sector_id)
                    .where(
                        Mandate.stage == DealStage.CLOSED_WON.value,
                        and_(Mandate.closing_date >= start, Mandate.closing_date <= end),
                    ),
                )
            )
        ).all()
        durations = [Decimal((m.closing_date - m.created_at.date()).days) for m, _ in closed if m.closing_date]
        sectors: dict[int, tuple[str, list[Decimal]]] = {}
        for mandate, label in closed:
            if mandate.ev_ebitda is not None:
                sectors.setdefault(mandate.sector_id, (label, []))[1].append(mandate.ev_ebitda)
        return {
            "period_start": start,
            "period_end": end,
            "pitches": len(decided),
            "won": won,
            "lost": len(lost),
            "win_rate": to_cents(Decimal(won) * 100 / len(decided)) if decided else None,
            "top_lost_reasons": [{"reason": reason, "count": count} for reason, count in top],
            "closed_deals": len(closed),
            "average_duration_days": to_cents(sum(durations, Decimal("0")) / len(durations)) if durations else None,
            "ev_ebitda_by_sector": [
                {
                    "sector_id": sector_id,
                    "sector": label,
                    "deals": len(values),
                    "average_ev_ebitda": to_cents(sum(values, Decimal("0")) / len(values)),
                }
                for sector_id, (label, values) in sorted(sectors.items(), key=lambda item: item[1][0])
            ],
        }


def _anonymous(hidden: list[_Deal]) -> list[_Deal]:
    """Hidden deals, only when there are enough of them that no single one can be singled out."""
    return hidden if len(hidden) >= HIDDEN_CELL_MINIMUM else []


def or_none_expiry(column: Any, now: datetime) -> Any:
    return column.is_(None) | (column > now)


async def _retainers_paid(db: AsyncSession, mandate_id: int) -> Decimal:
    rows = await db.execute(
        select(Invoice.amount).where(
            Invoice.mandate_id == mandate_id, Invoice.type == InvoiceType.RETAINER.value, Invoice.paid_date.is_not(None)
        )
    )
    return sum(rows.scalars(), Decimal("0"))
