"""Fees (DEAL-05), their visibility (AUTHZ-06) and invoices (REP-07).

Amounts are in EUR; enterprise values are in EUR thousands, as everywhere in the CRM.
"""

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService, audit_export
from ..common.exceptions import DealForbiddenError, InvoiceNotFoundError, ValidationError
from ..common.money import to_cents
from ..common.spreadsheet import safe_dict
from ..mandate.models import DealLink, Mandate
from ..mandate.pipeline import ENGAGEMENT_LETTER_LABEL
from ..mandate.policy import CLOSER_ROLES, DealGrant, DealPolicy
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..role.authorization import has_permission
from ..role.models import Role
from ..role.permissions import Permission
from ..task.models import Task
from ..user.models import User
from .models import FeeTerms, Invoice, InvoiceTask
from .schemas import FeeTermsValues, InvoiceCreate, InvoiceType, InvoiceUpdate, LehmanTier, SuccessFeeKind

THOUSAND = Decimal("1000")
AMENDED_LETTER_LABEL = "Amended engagement letter"
INVOICE_TASK_DUE = timedelta(days=7)
# Fields whose change after engagement needs a reason and the amended letter (DEAL-05 c3).
TERM_FIELDS = (
    "retainer_monthly",
    "success_fee_kind",
    "success_fee_percent",
    "success_fee_fixed",
    "minimum_fee",
    "lehman_tiers",
    "retainers_creditable",
)
EXPORT_COLUMNS = (
    "code_name",
    "retainer_monthly",
    "success_fee_kind",
    "success_fee_percent",
    "success_fee_fixed",
    "minimum_fee",
    "retainers_creditable",
    "retainers_paid",
    "expected_fee",
    "final_fee",
)


def expected_success_fee(terms: FeeTermsValues, ev_thousands: Decimal) -> Decimal:
    """The success fee on an EV, before crediting retainers: never below the minimum fee."""
    ev = ev_thousands * THOUSAND
    if terms.success_fee_kind == SuccessFeeKind.FIXED:
        fee = terms.success_fee_fixed or Decimal("0")
    elif terms.success_fee_kind == SuccessFeeKind.PERCENT:
        fee = ev * (terms.success_fee_percent or Decimal("0")) / 100
    else:
        fee, floor = Decimal("0"), Decimal("0")
        for tier in terms.lehman_tiers:
            ceiling = ev if tier.up_to is None else min(ev, tier.up_to * THOUSAND)
            if ceiling > floor:
                fee += (ceiling - floor) * tier.percent / 100
            if tier.up_to is not None:
                floor = max(floor, tier.up_to * THOUSAND)
    return to_cents(max(fee, terms.minimum_fee))


def net_fee(terms: FeeTermsValues, ev_thousands: Decimal, retainers_paid: Decimal) -> Decimal:
    fee = expected_success_fee(terms, ev_thousands)
    if terms.retainers_creditable:
        fee = max(fee - retainers_paid, Decimal("0"))
    return to_cents(fee)


def _values_of(row: FeeTerms) -> FeeTermsValues:
    return FeeTermsValues(
        retainer_monthly=row.retainer_monthly,
        success_fee_kind=SuccessFeeKind(row.success_fee_kind),
        success_fee_percent=row.success_fee_percent,
        success_fee_fixed=row.success_fee_fixed,
        minimum_fee=row.minimum_fee,
        lehman_tiers=[LehmanTier.model_validate(tier) for tier in row.lehman_tiers],
        retainers_creditable=row.retainers_creditable,
    )


def _snapshot(values: FeeTermsValues) -> dict[str, Any]:
    def text(value: Any) -> Any:
        if isinstance(value, Decimal):
            return f"{to_cents(value):.2f}"
        return value

    snapshot = {field: text(getattr(values, field)) for field in TERM_FIELDS if field != "lehman_tiers"}
    snapshot["success_fee_kind"] = values.success_fee_kind.value
    snapshot["lehman_tiers"] = [
        {"up_to": None if tier.up_to is None else f"{tier.up_to:.2f}", "percent": f"{tier.percent:.3f}"}
        for tier in values.lehman_tiers
    ]
    return snapshot


def can_edit_fees(grant: DealGrant) -> bool:
    """Back-office edits any deal's fees; a partner only on deals they are a partner on (ROLE-01 c5)."""
    if grant.is_closed:
        return False
    if has_permission(grant.user, Permission.FEES_EDIT):
        return True
    return (
        has_permission(grant.user, Permission.FEES_EDIT_OWN_DEALS)
        and grant.membership is not None
        and grant.membership.role in CLOSER_ROLES
    )


class FeeService:
    def __init__(self, notifications: NotificationService, audit: AuditService | None = None) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()

    async def _terms(self, db: AsyncSession, mandate_id: int) -> FeeTerms | None:
        return (await db.execute(select(FeeTerms).where(FeeTerms.mandate_id == mandate_id))).scalar_one_or_none()

    async def retainers_paid(self, db: AsyncSession, mandate_id: int) -> Decimal:
        total = (
            await db.execute(
                select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                    Invoice.mandate_id == mandate_id,
                    Invoice.type == InvoiceType.RETAINER.value,
                    Invoice.paid_date.is_not(None),
                )
            )
        ).scalar_one()
        return to_cents(Decimal(total))

    async def engaged(self, db: AsyncSession, mandate_id: int) -> bool:
        labels = (await db.execute(select(DealLink.label).where(DealLink.mandate_id == mandate_id))).scalars()
        return ENGAGEMENT_LETTER_LABEL.lower() in {label.strip().lower() for label in labels}

    async def _read(self, db: AsyncSession, mandate: Mandate, row: FeeTerms | None, can_edit: bool) -> dict[str, Any]:
        values = _values_of(row) if row else FeeTermsValues(success_fee_percent=Decimal("0"))
        paid = await self.retainers_paid(db, mandate.id)
        return {
            "mandate_id": mandate.id,
            "code_name": mandate.code_name,
            **values.model_dump(exclude={"change_reason", "amended_letter_url"}),
            "retainers_paid": paid,
            "expected_fee": net_fee(values, mandate.estimated_ev, paid),
            "final_fee": row.final_fee if row else None,
            "engaged": await self.engaged(db, mandate.id),
            "can_edit": can_edit,
        }

    async def read(self, db: AsyncSession, grant: DealGrant) -> dict[str, Any]:
        return await self._read(db, grant.mandate, await self._terms(db, grant.mandate.id), can_edit_fees(grant))

    async def save(self, db: AsyncSession, grant: DealGrant, values: FeeTermsValues, context: AuditContext) -> dict[str, Any]:
        if not can_edit_fees(grant):
            raise DealForbiddenError("Only back-office or a partner on the deal edits its fees")
        assert context.user_id is not None
        mandate = grant.mandate
        row = await self._terms(db, mandate.id)
        old = _snapshot(_values_of(row)) if row else None
        new = _snapshot(values)
        if old == new:
            return await self.read(db, grant)
        now = context.clock.now()
        engaged = await self.engaged(db, mandate.id)
        if row is not None and engaged:
            if not (values.change_reason or "").strip():
                raise ValidationError("Say why the fees changed after engagement", field="change_reason")
            if not values.amended_letter_url:
                raise ValidationError("Attach the amended engagement letter link", field="amended_letter_url")
            db.add(
                DealLink(
                    mandate_id=mandate.id,
                    label=AMENDED_LETTER_LABEL,
                    url=values.amended_letter_url,
                    added_by=context.user_id,
                    added_at=now,
                )
            )
        if row is None:
            row = FeeTerms(
                mandate_id=mandate.id,
                retainer_monthly=values.retainer_monthly,
                success_fee_kind=values.success_fee_kind.value,
                minimum_fee=values.minimum_fee,
                retainers_creditable=values.retainers_creditable,
                updated_by=context.user_id,
                updated_at=now,
            )
            db.add(row)
        row.retainer_monthly = values.retainer_monthly
        row.success_fee_kind = values.success_fee_kind.value
        row.success_fee_percent = values.success_fee_percent
        row.success_fee_fixed = values.success_fee_fixed
        row.minimum_fee = values.minimum_fee
        row.lehman_tiers = new["lehman_tiers"]
        row.retainers_creditable = values.retainers_creditable
        row.updated_by = context.user_id
        row.updated_at = now
        changes = dict(new)
        if engaged and old is not None:
            changes["change_reason"] = (values.change_reason or "").strip()
            changes["amended_letter_url"] = values.amended_letter_url
        # Fee history is its own record type, so the deal history (read by analysts) never shows it.
        self.audit.record(
            db,
            context,
            "fee.changed" if old is not None else "fee.set",
            record_type="fee_terms",
            record_id=mandate.id,
            old_values=old,
            new_values=changes,
        )
        await db.commit()
        return await self.read(db, grant)

    async def list_visible(
        self, db: AsyncSession, user: dict[str, Any], now: datetime, min_expected_fee: Decimal | None
    ) -> list[dict[str, Any]]:
        """Fees of the deals the caller reads; back-office (deals.read_summary) reads every deal's fees."""
        query = select(Mandate, FeeTerms).join(FeeTerms, FeeTerms.mandate_id == Mandate.id).order_by(Mandate.code_name)
        if not has_permission(user, Permission.DEALS_READ_SUMMARY):
            query = DealPolicy(now).visible(user, query)
        rows = []
        for mandate, terms in (await db.execute(query)).all():
            read = await self._read(db, mandate, terms, can_edit=False)
            if min_expected_fee is None or read["expected_fee"] >= min_expected_fee:
                rows.append(read)
        return rows

    def export_csv(self, rows: list[dict[str, Any]], context: AuditContext, db: AsyncSession, filters: dict[str, Any]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(safe_dict({**row, "success_fee_kind": SuccessFeeKind(row["success_fee_kind"]).value}))
        audit_export(db, context, "fees", record_type="fee_terms", filters=filters, rows=len(rows))
        return buffer.getvalue()

    # Invoices (REP-07)

    async def invoices(self, db: AsyncSession, mandate_id: int) -> list[Invoice]:
        query = select(Invoice).where(Invoice.mandate_id == mandate_id).order_by(Invoice.sent_date, Invoice.id)
        return list((await db.execute(query)).scalars())

    async def record_invoice(self, db: AsyncSession, grant: DealGrant, values: InvoiceCreate, context: AuditContext) -> Invoice:
        assert context.user_id is not None
        _check_dates(values.sent_date, values.paid_date)
        now = context.clock.now()
        invoice = Invoice(
            mandate_id=grant.mandate.id,
            type=values.type.value,
            amount=values.amount,
            sent_date=values.sent_date,
            recorded_by=context.user_id,
            created_at=now,
            paid_date=values.paid_date,
        )
        db.add(invoice)
        await db.flush()
        if values.type == InvoiceType.SUCCESS_FEE:
            open_tasks = select(InvoiceTask.task_id).where(InvoiceTask.mandate_id == grant.mandate.id)
            for task in (await db.execute(select(Task).where(Task.id.in_(open_tasks), Task.completed_at.is_(None)))).scalars():
                task.completed_at = now
        self.audit.record(
            db,
            context,
            "invoice.recorded",
            record_type="fee_terms",
            record_id=grant.mandate.id,
            new_values={"invoice_id": invoice.id, **_invoice_values(invoice)},
        )
        await db.commit()
        return invoice

    async def update_invoice(
        self, db: AsyncSession, grant: DealGrant, invoice_id: int, values: InvoiceUpdate, context: AuditContext
    ) -> Invoice:
        invoice = await db.get(Invoice, invoice_id)
        if invoice is None or invoice.mandate_id != grant.mandate.id:
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
        _check_dates(invoice.sent_date, values.paid_date)
        old = _invoice_values(invoice)
        invoice.paid_date = values.paid_date
        self.audit.record(
            db,
            context,
            "invoice.updated",
            record_type="fee_terms",
            record_id=grant.mandate.id,
            old_values={"invoice_id": invoice.id, **old},
            new_values={"invoice_id": invoice.id, **_invoice_values(invoice)},
        )
        await db.commit()
        return invoice


def _check_dates(sent: date, paid: date | None) -> None:
    if paid is not None and paid < sent:
        raise ValidationError("An invoice cannot be paid before it was sent", field="paid_date")


def _invoice_values(invoice: Invoice) -> dict[str, Any]:
    return {
        "type": invoice.type,
        "amount": f"{invoice.amount:.2f}",
        "sent_date": invoice.sent_date.isoformat(),
        "paid_date": invoice.paid_date.isoformat() if invoice.paid_date else None,
    }


# Closing (DEAL-05 c2): registered with the pipeline in interfaces/main.


async def on_closed_won(db: AsyncSession, mandate: Mandate, now: datetime, notifications: NotificationService) -> None:
    service = FeeService(notifications)
    row = await service._terms(db, mandate.id)
    if row is not None and mandate.final_ev is not None:
        row.final_fee = net_fee(_values_of(row), mandate.final_ev, await service.retainers_paid(db, mandate.id))
    due = (now + INVOICE_TASK_DUE).date()
    for user in await _back_office(db):
        # No mandate_id: back-office holds the task without being on the deal team. Code name only.
        task = Task(
            title=f"Invoice the success fee for {mandate.code_name}",
            assignee_id=user.id,
            created_by=mandate.lead_partner_id,
            due_date=due,
            recurrence="none",
            created_at=now,
            record_type="mandate",
            record_id=mandate.id,
        )
        db.add(task)
        await db.flush()
        db.add(InvoiceTask(mandate_id=mandate.id, task_id=task.id))
        await notifications.add(
            db,
            Message(
                user_id=user.id,
                email=user.email,
                kind=EventKind.TASK_ASSIGNED.value,
                title=f"{mandate.code_name}: invoice the success fee",
                body=f"{mandate.code_name} closed. Record the success-fee invoice on the deal.",
                link=f"/deals/{mandate.id}",
            ),
            now,
        )


async def _back_office(db: AsyncSession) -> list[User]:
    roles = (await db.execute(select(Role.id, Role.permissions).where(Role.is_deleted.is_(False)))).all()
    role_ids = [role_id for role_id, permissions in roles if Permission.INVOICES_MANAGE.value in (permissions or [])]
    if not role_ids:
        return []
    query = select(User).where(User.role_id.in_(role_ids), User.is_deleted.is_(False)).order_by(User.id)
    return list((await db.execute(query)).scalars())
