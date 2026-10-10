"""The pipeline (DEAL-02/04/06/08): stage moves through exit criteria, closing, reopening, milestones."""

from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import (
    DealForbiddenError,
    MilestoneNotFoundError,
    StageCriterionExistsError,
    StageCriterionNotFoundError,
    ValidationError,
)
from ..notification.service import Message, NotificationService
from ..user.models import User
from .models import DealLink, DealTeamMember, Mandate, Milestone, StageCriterion
from .policy import DealGrant
from .schemas import (
    CriterionKind,
    MandateClose,
    MandateReopen,
    MilestoneCreate,
    MilestoneUpdate,
    Outcome,
    StageCriterionCreate,
    StageMove,
)
from .stages import DealStage, stages_for

CLOSED_STAGES = frozenset({DealStage.CLOSED_WON, DealStage.ABORTED})
ENGAGEMENT_LETTER_LABEL = "Engagement letter"
MILESTONE_LEAD = timedelta(days=3)

# Fields an admin may require before a deal leaves a stage, with their user-facing names.
REQUIRABLE_FIELDS: dict[str, str] = {
    "target_id": "Target",
    "estimated_ev": "Estimated EV",
    "sector_id": "Sector",
    "client_id": "Client",
}

# The KYC status comes from the compliance slice (ORI-05, ticket #9). Until it plugs in its own
# check, no KYC is approved, so the built-in Preparation gate holds every deal there.
KycCheck = Callable[[AsyncSession, Mandate], Awaitable[bool]]


async def no_kyc_yet(db: AsyncSession, mandate: Mandate) -> bool:
    return False


_kyc_check: KycCheck = no_kyc_yet


def set_kyc_check(check: KycCheck) -> None:
    global _kyc_check
    _kyc_check = check


class StaleVersion(Exception):
    pass


class StageBlockedError(Exception):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def describe(kind: str, value: str | None) -> str:
    if kind == CriterionKind.FIELD:
        return f"Fill in {REQUIRABLE_FIELDS.get(value or '', value)}."
    if kind == CriterionKind.LINK_LABEL:
        return f"Add a document link labelled “{value}”."
    return "Signed engagement letter and approved KYC."


def days_late(milestone: Milestone, today: date) -> int:
    reference = milestone.actual_date or today
    return max((reference - milestone.planned_date).days, 0)


def milestone_read(milestone: Milestone, today: date) -> dict[str, Any]:
    late = days_late(milestone, today)
    return {
        "id": milestone.id,
        "name": milestone.name,
        "planned_date": milestone.planned_date.isoformat(),
        "actual_date": milestone.actual_date.isoformat() if milestone.actual_date else None,
        "late": late > 0,
        "days_late": late,
    }


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


class PipelineService:
    def __init__(self, notifications: NotificationService, audit: AuditService | None = None) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()

    # Exit criteria (DEAL-08)

    async def seed_builtin_gate(self, db: AsyncSession, now: datetime) -> None:
        """The engagement letter / KYC gate on Preparation (ORI-05). Seeded once; admins may disable it."""
        exists = (
            await db.execute(select(StageCriterion.id).where(StageCriterion.kind == CriterionKind.KYC_ENGAGEMENT.value))
        ).first()
        if exists is None:
            db.add(
                StageCriterion(
                    stage=DealStage.PREPARATION.value,
                    kind=CriterionKind.KYC_ENGAGEMENT.value,
                    value_key="",
                    created_at=now,
                )
            )
            await db.commit()

    async def criteria(self, db: AsyncSession, now: datetime) -> list[dict[str, Any]]:
        await self.seed_builtin_gate(db, now)
        rows = (
            await db.execute(select(StageCriterion).where(StageCriterion.enabled.is_(True)).order_by(StageCriterion.id))
        ).scalars()
        order = {stage.value: index for index, stage in enumerate(DealStage)}
        return sorted(
            (
                {"id": c.id, "stage": c.stage, "kind": c.kind, "value": c.value, "description": describe(c.kind, c.value)}
                for c in rows
            ),
            key=lambda item: (order[item["stage"]], item["id"]),
        )

    async def add_criterion(self, db: AsyncSession, values: StageCriterionCreate, context: AuditContext) -> dict[str, Any]:
        if values.stage in CLOSED_STAGES:
            raise ValidationError("A closed stage has no exit", field="stage")
        value = (values.value or "").strip() or None
        if values.kind == CriterionKind.FIELD and value not in REQUIRABLE_FIELDS:
            raise ValidationError(f"Choose one of: {', '.join(REQUIRABLE_FIELDS)}", field="value")
        if values.kind == CriterionKind.LINK_LABEL and value is None:
            raise ValidationError("Name the document link label", field="value")
        if values.kind == CriterionKind.KYC_ENGAGEMENT:
            value = None
        key = (value or "").lower()
        existing = (
            await db.execute(
                select(StageCriterion).where(
                    StageCriterion.stage == values.stage.value,
                    StageCriterion.kind == values.kind.value,
                    StageCriterion.value_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None and existing.enabled:
            raise StageCriterionExistsError("Criterion exists")
        if existing is not None:
            existing.enabled = True
            criterion = existing
        else:
            criterion = StageCriterion(
                stage=values.stage.value, kind=values.kind.value, value_key=key, value=value, created_at=context.clock.now()
            )
            db.add(criterion)
        try:
            await db.flush()
        except IntegrityError as error:
            await db.rollback()
            raise StageCriterionExistsError("Criterion exists") from error
        self.audit.record(
            db,
            context,
            "stage_criterion.added",
            record_type="stage_criterion",
            record_id=criterion.id,
            new_values={"stage": criterion.stage, "kind": criterion.kind, "value": criterion.value},
        )
        await db.commit()
        return {
            "id": criterion.id,
            "stage": criterion.stage,
            "kind": criterion.kind,
            "value": criterion.value,
            "description": describe(criterion.kind, criterion.value),
        }

    async def remove_criterion(self, db: AsyncSession, criterion_id: int, context: AuditContext) -> None:
        criterion = await db.get(StageCriterion, criterion_id)
        if criterion is None or not criterion.enabled:
            raise StageCriterionNotFoundError("Not found")
        criterion.enabled = False
        self.audit.record(
            db,
            context,
            "stage_criterion.removed",
            record_type="stage_criterion",
            record_id=criterion.id,
            old_values={"stage": criterion.stage, "kind": criterion.kind, "value": criterion.value},
        )
        await db.commit()

    async def missing_criteria(self, db: AsyncSession, mandate: Mandate, stages: list[str]) -> list[str]:
        """What stops the deal leaving every stage in `stages`, as user-facing reasons."""
        criteria = (
            await db.execute(
                select(StageCriterion)
                .where(StageCriterion.enabled.is_(True), StageCriterion.stage.in_(stages))
                .order_by(StageCriterion.id)
            )
        ).scalars()
        labels = {
            label.strip().lower()
            for label in (await db.execute(select(DealLink.label).where(DealLink.mandate_id == mandate.id))).scalars()
        }
        reasons: list[str] = []
        for criterion in criteria:
            if criterion.kind == CriterionKind.FIELD:
                if getattr(mandate, criterion.value or "", None) is None:
                    reasons.append(describe(criterion.kind, criterion.value))
            elif criterion.kind == CriterionKind.LINK_LABEL:
                if criterion.value_key not in labels:
                    reasons.append(describe(criterion.kind, criterion.value))
            else:
                if ENGAGEMENT_LETTER_LABEL.lower() not in labels:
                    reasons.append(f"Add the signed engagement letter as a document link labelled “{ENGAGEMENT_LETTER_LABEL}”.")
                if not await _kyc_check(db, mandate):
                    reasons.append("KYC must be approved.")
        return list(dict.fromkeys(reasons))

    # Stage moves (DEAL-02)

    async def move(self, db: AsyncSession, grant: DealGrant, values: StageMove, context: AuditContext) -> None:
        mandate = grant.mandate
        await self.seed_builtin_gate(db, context.clock.now())
        await db.refresh(mandate, with_for_update=True)
        if values.version != mandate.version:
            raise StaleVersion()
        if values.stage in CLOSED_STAGES:
            raise ValidationError("Close the deal to mark it Closed won or Aborted", field="stage")
        order = [stage.value for stage in stages_for(mandate.type)]
        source, target = order.index(mandate.stage), order.index(values.stage.value)
        if source == target:
            return
        reason = (values.reason or "").strip() or None
        if target < source and reason is None:
            raise ValidationError("Say why the deal moves back a stage", field="reason")
        if target > source:
            reasons = await self.missing_criteria(db, mandate, order[source:target])
            if reasons:
                await db.rollback()
                raise StageBlockedError(reasons)
        now = context.clock.now()
        old = mandate.stage
        mandate.stage = values.stage.value
        mandate.stage_changed_at = now
        mandate.updated_at = now
        mandate.version += 1
        new_values: dict[str, Any] = {"stage": mandate.stage}
        if reason:
            new_values["stage_reason"] = reason
        self.audit.record(
            db,
            context,
            "mandate.updated",
            record_type="mandate",
            record_id=mandate.id,
            old_values={"stage": old},
            new_values=new_values,
        )
        await db.commit()

    # Closing (DEAL-06)

    async def close(self, db: AsyncSession, grant: DealGrant, values: MandateClose, context: AuditContext) -> None:
        mandate = grant.mandate
        if not grant.is_closer:
            raise DealForbiddenError("Only a partner on the deal closes it")
        await db.refresh(mandate, with_for_update=True)
        if values.version != mandate.version:
            raise StaleVersion()
        if values.outcome == Outcome.CLOSED_WON:
            required = {
                "final_ev": values.final_ev,
                "buyer": None if _blank(values.buyer) else values.buyer,
                "ev_ebitda": values.ev_ebitda,
                "closing_date": values.closing_date,
                "tombstone_allowed": values.tombstone_allowed,
            }
            for field, value in required.items():
                if value is None:
                    raise ValidationError(f"{field.replace('_', ' ').capitalize()} is required to close as won", field=field)
            assert values.final_ev is not None
            assert values.ev_ebitda is not None
            assert values.buyer is not None
            mandate.final_ev = Decimal(values.final_ev).quantize(Decimal("0.01"))
            mandate.buyer = values.buyer.strip()
            mandate.ev_ebitda = Decimal(values.ev_ebitda).quantize(Decimal("0.01"))
            mandate.closing_date = values.closing_date
            mandate.tombstone_allowed = values.tombstone_allowed
            mandate.abort_reason = None
        else:
            if _blank(values.abort_reason):
                raise ValidationError("Say why the deal was aborted", field="abort_reason")
            assert values.abort_reason is not None
            mandate.abort_reason = values.abort_reason.strip()
        now = context.clock.now()
        old_stage = mandate.stage
        mandate.stage_before_close = old_stage
        mandate.stage = values.outcome.value
        mandate.stage_changed_at = now
        mandate.closed_at = now
        mandate.updated_at = now
        mandate.version += 1
        outcome = {
            "stage": mandate.stage,
            "final_ev": f"{mandate.final_ev:.2f}" if mandate.final_ev is not None else None,
            "buyer": mandate.buyer,
            "ev_ebitda": f"{mandate.ev_ebitda:.2f}" if mandate.ev_ebitda is not None else None,
            "closing_date": mandate.closing_date.isoformat() if mandate.closing_date else None,
            "tombstone_allowed": mandate.tombstone_allowed,
            "abort_reason": mandate.abort_reason,
        }
        self.audit.record(
            db,
            context,
            "mandate.closed",
            record_type="mandate",
            record_id=mandate.id,
            old_values={"stage": old_stage},
            new_values={key: value for key, value in outcome.items() if value is not None},
        )
        await db.commit()

    async def reopen(self, db: AsyncSession, grant: DealGrant, values: MandateReopen, context: AuditContext) -> None:
        mandate = grant.mandate
        await db.refresh(mandate, with_for_update=True)
        if values.version != mandate.version:
            raise StaleVersion()
        if mandate.closed_at is None:
            raise ValidationError("This deal is not closed", field="reason")
        if _blank(values.reason):
            raise ValidationError("Say why the deal is reopened", field="reason")
        assert values.reason is not None
        now = context.clock.now()
        old_stage = mandate.stage
        mandate.stage = mandate.stage_before_close or DealStage.CLOSING.value
        mandate.stage_before_close = None
        mandate.closed_at = None
        mandate.abort_reason = None
        mandate.stage_changed_at = now
        mandate.updated_at = now
        mandate.version += 1
        self.audit.record(
            db,
            context,
            "mandate.reopened",
            record_type="mandate",
            record_id=mandate.id,
            old_values={"stage": old_stage},
            new_values={"stage": mandate.stage, "reason": values.reason.strip()},
        )
        await db.commit()

    # Milestones (DEAL-04)

    async def milestones(self, db: AsyncSession, mandate_id: int, today: date) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Milestone).where(Milestone.mandate_id == mandate_id).order_by(Milestone.planned_date, Milestone.id)
            )
        ).scalars()
        return [milestone_read(row, today) for row in rows]

    async def add_milestone(
        self, db: AsyncSession, grant: DealGrant, values: MilestoneCreate, context: AuditContext
    ) -> dict[str, Any]:
        now = context.clock.now()
        milestone = Milestone(
            mandate_id=grant.mandate.id,
            name=values.name.strip(),
            planned_date=values.planned_date,
            created_at=now,
            actual_date=values.actual_date,
        )
        db.add(milestone)
        await db.flush()
        self.audit.record(
            db,
            context,
            "milestone.added",
            record_type="mandate",
            record_id=grant.mandate.id,
            new_values=_milestone_values(milestone),
        )
        await db.commit()
        return milestone_read(milestone, now.date())

    async def update_milestone(
        self, db: AsyncSession, grant: DealGrant, milestone_id: int, values: MilestoneUpdate, context: AuditContext
    ) -> dict[str, Any]:
        milestone = await db.get(Milestone, milestone_id)
        if milestone is None or milestone.mandate_id != grant.mandate.id:
            raise MilestoneNotFoundError("Milestone not found")
        changes = values.model_dump(exclude_unset=True)
        if "name" in changes and _blank(changes["name"]):
            raise ValidationError("Name the milestone", field="name")
        if "planned_date" in changes and changes["planned_date"] is None:
            raise ValidationError("A milestone needs a planned date", field="planned_date")
        old = _milestone_values(milestone)
        for key, value in changes.items():
            setattr(milestone, key, value.strip() if key == "name" else value)
        if "planned_date" in changes and old["planned_date"] != milestone.planned_date.isoformat():
            milestone.reminded_at = None
        self.audit.record(
            db,
            context,
            "milestone.updated",
            record_type="mandate",
            record_id=grant.mandate.id,
            old_values=old,
            new_values=_milestone_values(milestone),
        )
        await db.commit()
        return milestone_read(milestone, context.clock.now().date())

    async def remove_milestone(self, db: AsyncSession, grant: DealGrant, milestone_id: int, context: AuditContext) -> None:
        milestone = await db.get(Milestone, milestone_id)
        if milestone is None or milestone.mandate_id != grant.mandate.id:
            raise MilestoneNotFoundError("Milestone not found")
        await db.delete(milestone)
        self.audit.record(
            db,
            context,
            "milestone.removed",
            record_type="mandate",
            record_id=grant.mandate.id,
            old_values=_milestone_values(milestone),
        )
        await db.commit()

    async def remind_due_milestones(self, db: AsyncSession, now: datetime) -> None:
        """Tells the deal team about every open milestone due within 3 days, once per planned date."""
        horizon = now.date() + MILESTONE_LEAD
        due = (
            await db.execute(
                select(Milestone, Mandate)
                .join(Mandate, Mandate.id == Milestone.mandate_id)
                .where(
                    Milestone.actual_date.is_(None),
                    Milestone.reminded_at.is_(None),
                    Milestone.planned_date <= horizon,
                    Milestone.planned_date >= now.date(),
                    Mandate.closed_at.is_(None),
                )
            )
        ).all()
        for milestone, mandate in due:
            team = (
                await db.execute(
                    select(User)
                    .join(DealTeamMember, DealTeamMember.user_id == User.id)
                    .where(
                        DealTeamMember.mandate_id == mandate.id,
                        User.is_deleted.is_(False),
                        (DealTeamMember.expires_at.is_(None)) | (DealTeamMember.expires_at > now),
                    )
                )
            ).scalars()
            when = milestone.planned_date.isoformat()
            for user in team:
                await self.notifications.add(
                    db,
                    Message(
                        user_id=user.id,
                        email=user.email,
                        kind="milestone.due",
                        title=f"{mandate.code_name}: a milestone is due on {when}",
                        body=f"A milestone of {mandate.code_name} is planned for {when}. Open the deal to update it.",
                        link=f"/deals/{mandate.id}",
                        mandate_id=mandate.id,
                    ),
                    now,
                )
            milestone.reminded_at = now
        await db.commit()
        await self.notifications.flush_emails()


def _milestone_values(milestone: Milestone) -> dict[str, Any]:
    return {
        "name": milestone.name,
        "planned_date": milestone.planned_date.isoformat(),
        "actual_date": milestone.actual_date.isoformat() if milestone.actual_date else None,
    }
