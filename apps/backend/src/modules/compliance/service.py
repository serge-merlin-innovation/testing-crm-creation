"""Conflict check (AUTHZ-05) and KYC / engagement letter gate (ORI-05).

The mandate module calls in through two hooks installed by `install()`: the conflict check on
creation and the KYC answer of the Preparation gate (decision 14).
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, func, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import ValidationError
from ..company.models import Company
from ..company.service import normalize_name
from ..mandate import pipeline as mandate_pipeline
from ..mandate import service as mandate_service
from ..mandate.models import Mandate
from ..mandate.policy import DealGrant
from ..mandate.schemas import ConflictStatus
from ..mandate.stages import DealStage
from ..notification.ports import LoggingEmailSender
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..role.permissions import Permission
from ..task.models import Task
from ..user.models import User
from .models import ConflictHit, ConflictReview, DealCounterparty, KycRecord
from .schemas import ConflictDecision, ConflictDecisionKind, CounterpartyCreate, KycReview, KycStatus, Unfreeze

# Closed and aborted deals stay in the conflict check this long (AUTHZ-05 c1: 24 months).
HISTORY_WINDOW = timedelta(days=730)
# pg_trgm similarity of the legal-form-stripped, unaccented names at or above which two companies match.
NAME_SIMILARITY = 0.6
REVIEW_WORKING_DAYS = 5
KYC_VALID_FOR = timedelta(days=365)


def add_working_days(start: datetime, days: int) -> datetime:
    current = start
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days -= 1
    return current


def _blank(text: str | None) -> bool:
    return text is None or not text.strip()


async def _users_with(db: AsyncSession, permission: Permission) -> list[User]:
    users = (await db.execute(select(User).where(User.is_deleted.is_(False), User.role_id.is_not(None)))).scalars()
    return [user for user in users if permission.value in (user.permissions or [])]


class ConflictService:
    def __init__(self, notifications: NotificationService | None = None, audit: AuditService | None = None) -> None:
        self.notifications = notifications or NotificationService(LoggingEmailSender())
        self.audit = audit or AuditService()

    # The check

    async def _group(self, db: AsyncSession, company_id: int) -> list[Company]:
        """The company with every company linked to it through parent links (CO-03)."""
        root = await db.get(Company, company_id)
        assert root is not None
        seen = {root.id}
        while root.parent_id is not None and root.parent_id not in seen:
            parent = await db.get(Company, root.parent_id)
            if parent is None:
                break
            root = parent
            seen.add(root.id)
        members, frontier = {root.id: root}, [root.id]
        while frontier:
            children = (await db.execute(select(Company).where(Company.parent_id.in_(frontier)))).scalars().all()
            frontier = [child.id for child in children if child.id not in members]
            members.update({child.id: child for child in children})
        members.setdefault(company_id, await db.get(Company, company_id))  # type: ignore[arg-type]
        return list(members.values())

    def _parties(self) -> Any:
        return union_all(
            select(Mandate.id.label("mandate_id"), Mandate.client_id.label("company_id"), literal("client").label("role")),
            select(Mandate.id, Mandate.target_id, literal("target")).where(Mandate.target_id.is_not(None)),
            select(DealCounterparty.mandate_id, DealCounterparty.company_id, literal("counterparty")),
        ).subquery()

    async def find_hits(
        self, db: AsyncSession, mandate: Mandate, parties: list[tuple[int, str]], now: datetime
    ) -> list[ConflictHit]:
        """Hits for `parties` [(company_id, role on this deal)] against active deals and those closed or aborted
        in the window. Every shared company is a potential conflict, a repeat client included: compliance decides."""
        others = self._parties()
        hits: dict[tuple[int, int], ConflictHit] = {}
        for company_id, role in parties:
            for member in await self._group(db, company_id):
                name = normalize_name(member.name)
                matches: Select[Any] = (
                    select(others.c.mandate_id, others.c.company_id, others.c.role)
                    .join(Mandate, Mandate.id == others.c.mandate_id)
                    .join(Company, Company.id == others.c.company_id)
                    .where(
                        Mandate.id != mandate.id,
                        or_(Mandate.closed_at.is_(None), Mandate.closed_at >= now - HISTORY_WINDOW),
                        or_(
                            Company.id == member.id,
                            and_(
                                literal(bool(name)),
                                func.similarity(func.unaccent(Company.normalized_name), func.unaccent(name)) >= NAME_SIMILARITY,
                            ),
                        ),
                    )
                    .order_by(others.c.mandate_id)
                )
                for other_mandate_id, matched_id, other_role in (await db.execute(matches)).all():
                    key = (company_id, other_mandate_id)
                    if key in hits:
                        continue
                    hits[key] = ConflictHit(
                        review_id=0,
                        company_id=company_id,
                        matched_company_id=matched_id,
                        other_mandate_id=other_mandate_id,
                        role=role,
                        other_role=other_role,
                    )
        return list(hits.values())

    async def _add_counterparty(self, db: AsyncSession, mandate: Mandate, company_id: int, user_id: int, now: datetime) -> None:
        if await db.get(Company, company_id) is None:
            raise ValidationError(f"Company {company_id} does not exist", field="company_id")
        db.add(DealCounterparty(mandate_id=mandate.id, company_id=company_id, added_by=user_id, added_at=now))

    async def _open_review(self, db: AsyncSession, mandate: Mandate, hits: list[ConflictHit], context: AuditContext) -> None:
        now = context.clock.now()
        review = ConflictReview(mandate_id=mandate.id, opened_at=now)
        db.add(review)
        await db.flush()
        for hit in hits:
            hit.review_id = review.id
            db.add(hit)
        mandate.conflict_status = ConflictStatus.REVIEW.value
        # Only compliance sees what the deal conflicts with, so the deal's own history names no other deal.
        self.audit.record(
            db, context, "conflict.flagged", record_type="mandate", record_id=mandate.id, new_values={"hits": len(hits)}
        )

    async def check_new_mandate(
        self, db: AsyncSession, mandate: Mandate, counterparty_ids: list[int], context: AuditContext
    ) -> None:
        assert context.user_id is not None
        now = context.clock.now()
        parties = [(mandate.client_id, "client")]
        if mandate.target_id is not None:
            parties.append((mandate.target_id, "target"))
        for company_id in dict.fromkeys(counterparty_ids):
            await self._add_counterparty(db, mandate, company_id, context.user_id, now)
            parties.append((company_id, "counterparty"))
        await db.flush()
        hits = await self.find_hits(db, mandate, parties, now)
        if hits:
            await self._open_review(db, mandate, hits, context)

    async def add_counterparty(
        self, db: AsyncSession, grant: DealGrant, values: CounterpartyCreate, context: AuditContext
    ) -> dict[str, Any]:
        assert context.user_id is not None
        mandate = grant.mandate
        now = context.clock.now()
        await self._add_counterparty(db, mandate, values.company_id, context.user_id, now)
        try:
            await db.flush()
        except IntegrityError as error:
            await db.rollback()
            raise ValidationError("This company is already a counterparty of the deal", field="company_id") from error
        self.audit.record(
            db,
            context,
            "counterparty.added",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"company_id": values.company_id},
        )
        hits = await self.find_hits(db, mandate, [(values.company_id, "counterparty")], now)
        if hits:
            await self._open_review(db, mandate, hits, context)
        await db.commit()
        return next(c for c in await self.counterparties(db, mandate) if c["company_id"] == values.company_id)

    async def counterparties(self, db: AsyncSession, mandate: Mandate) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(DealCounterparty, Company.name)
                .join(Company, Company.id == DealCounterparty.company_id)
                .where(DealCounterparty.mandate_id == mandate.id)
                .order_by(Company.name)
            )
        ).all()
        return [
            {"company_id": row.company_id, "name": name, "added_at": row.added_at, "conflict_status": mandate.conflict_status}
            for row, name in rows
        ]

    # Compliance's view

    async def hits(self, db: AsyncSession, mandate_id: int) -> list[dict[str, Any]]:
        ours, theirs = aliased(Company), aliased(Company)
        other = aliased(Mandate)
        rows = (
            await db.execute(
                select(ConflictHit, ours.name, theirs.name, other.code_name, other.stage)
                .join(ConflictReview, ConflictReview.id == ConflictHit.review_id)
                .join(ours, ours.id == ConflictHit.company_id)
                .join(theirs, theirs.id == ConflictHit.matched_company_id)
                .join(other, other.id == ConflictHit.other_mandate_id)
                .where(ConflictReview.mandate_id == mandate_id)
                .order_by(ConflictHit.id)
            )
        ).all()
        return [
            {
                "company_id": hit.company_id,
                "company_name": our_name,
                "role": hit.role,
                "matched_company_id": hit.matched_company_id,
                "matched_company_name": their_name,
                "other_mandate_id": hit.other_mandate_id,
                "other_code_name": code_name,
                "other_role": hit.other_role,
                "other_stage": stage,
            }
            for hit, our_name, their_name, code_name, stage in rows
        ]

    async def open_reviews(self, db: AsyncSession) -> list[dict[str, Any]]:
        hit_count = select(func.count(ConflictHit.id)).where(ConflictHit.review_id == ConflictReview.id).scalar_subquery()
        rows = (
            await db.execute(
                select(ConflictReview, Mandate.code_name, hit_count)
                .join(Mandate, Mandate.id == ConflictReview.mandate_id)
                .where(ConflictReview.decision.is_(None))
                .order_by(ConflictReview.opened_at, ConflictReview.id)
            )
        ).all()
        return [
            {"mandate_id": review.mandate_id, "code_name": code_name, "opened_at": review.opened_at, "hits": count}
            for review, code_name, count in rows
        ]

    async def decide(
        self, db: AsyncSession, grant: DealGrant, values: ConflictDecision, context: AuditContext
    ) -> dict[str, Any]:
        assert context.user_id is not None
        mandate = grant.mandate
        if _blank(values.reason):
            raise ValidationError("Give the reason for the decision", field="reason")
        assert values.reason is not None
        reviews = (
            (
                await db.execute(
                    select(ConflictReview).where(ConflictReview.mandate_id == mandate.id, ConflictReview.decision.is_(None))
                )
            )
            .scalars()
            .all()
        )
        if not reviews:
            raise ValidationError("This deal has no conflict review waiting", field="decision")
        now = context.clock.now()
        reason = values.reason.strip()
        for review in reviews:
            review.decision = values.decision.value
            review.reason = reason
            review.decided_by = context.user_id
            review.decided_at = now
        old = {"conflict_status": mandate.conflict_status, "stage": mandate.stage}
        if values.decision == ConflictDecisionKind.CLEAR:
            mandate.conflict_status = ConflictStatus.CLEARED.value
            if mandate.stage == DealStage.CONFLICT_REVIEW.value:
                mandate.stage = DealStage.PREPARATION.value
                mandate.stage_changed_at = now
        else:
            mandate.conflict_status = ConflictStatus.REJECTED.value
            if mandate.closed_at is None:
                mandate.stage_before_close = mandate.stage
                mandate.stage = DealStage.ABORTED.value
                mandate.closed_at = now
                mandate.abort_reason = f"Conflict check rejected: {reason}"
                mandate.stage_changed_at = now
        mandate.updated_at = now
        mandate.version += 1
        self.audit.record(
            db,
            context,
            f"conflict.{'cleared' if values.decision == ConflictDecisionKind.CLEAR else 'rejected'}",
            record_type="mandate",
            record_id=mandate.id,
            old_values=old,
            new_values={"conflict_status": mandate.conflict_status, "stage": mandate.stage, "reason": reason},
        )
        await db.commit()
        approver = await db.get(User, context.user_id)
        assert approver is not None
        return {
            "conflict_status": mandate.conflict_status,
            "decision": values.decision,
            "reason": reason,
            "decided_by": approver.id,
            "decided_by_name": approver.name,
            "decided_at": now,
        }

    async def remind_overdue_reviews(self, db: AsyncSession, now: datetime) -> None:
        reviews = (
            await db.execute(
                select(ConflictReview, Mandate)
                .join(Mandate, Mandate.id == ConflictReview.mandate_id)
                .where(ConflictReview.decision.is_(None), ConflictReview.reminded_at.is_(None))
            )
        ).all()
        compliance = await _users_with(db, Permission.CONFLICTS_REGISTER)
        for review, mandate in reviews:
            if add_working_days(review.opened_at, REVIEW_WORKING_DAYS) > now:
                continue
            lead = await db.get(User, mandate.lead_partner_id)
            recipients = {user.id: user for user in [*compliance, *([lead] if lead else [])]}
            for user in recipients.values():
                await self.notifications.add(
                    db,
                    Message(
                        user_id=user.id,
                        email=user.email,
                        kind=EventKind.CONFLICT_REVIEW_OVERDUE.value,
                        title=f"Conflict review of {mandate.code_name} is waiting",
                        body=f"The conflict review of {mandate.code_name} has waited {REVIEW_WORKING_DAYS} working days "
                        "for a decision.",
                        link=f"/deals/{mandate.id}",
                        mandate_id=mandate.id,
                    ),
                    now,
                )
            review.reminded_at = now
        await db.commit()
        await self.notifications.flush_emails()


class KycService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def _record(self, db: AsyncSession, mandate_id: int) -> KycRecord | None:
        return (await db.execute(select(KycRecord).where(KycRecord.mandate_id == mandate_id))).scalar_one_or_none()

    async def read(self, db: AsyncSession, grant: DealGrant) -> dict[str, Any]:
        mandate = grant.mandate
        record = await self._record(db, mandate.id)
        reviewer = await db.get(User, record.reviewer_id) if record else None
        return {
            "status": record.status if record else KycStatus.NONE.value,
            "ubo_check": bool(record and record.ubo_check),
            "id_check": bool(record and record.id_check),
            "pep_sanctions_screening": bool(record and record.pep_sanctions_screening),
            "sanctions_hit": bool(record and record.sanctions_hit),
            "reviewed_at": record.reviewed_at if record else None,
            "approved_at": record.approved_at if record else None,
            "reviewer_id": reviewer.id if reviewer else None,
            "reviewer_name": reviewer.name if reviewer else None,
            "frozen": mandate.frozen_at is not None,
            "can_review": Permission.KYC_MANAGE.value in (grant.user.get("permissions") or []),
        }

    async def review(self, db: AsyncSession, grant: DealGrant, values: KycReview, context: AuditContext) -> dict[str, Any]:
        assert context.user_id is not None
        mandate = grant.mandate
        now = context.clock.now()
        if values.sanctions_hit:
            status = KycStatus.FROZEN
        elif values.ubo_check and values.id_check and values.pep_sanctions_screening:
            status = KycStatus.APPROVED
        else:
            status = KycStatus.PENDING
        record = await self._record(db, mandate.id)
        if record is None:
            record = KycRecord(
                mandate_id=mandate.id,
                status=status.value,
                ubo_check=values.ubo_check,
                id_check=values.id_check,
                pep_sanctions_screening=values.pep_sanctions_screening,
                sanctions_hit=values.sanctions_hit,
                reviewer_id=context.user_id,
                reviewed_at=now,
            )
            db.add(record)
        else:
            for field, value in values.model_dump().items():
                setattr(record, field, value)
            record.status = status.value
            record.reviewer_id = context.user_id
            record.reviewed_at = now
        record.approved_at = now if status == KycStatus.APPROVED else None
        self.audit.record(
            db,
            context,
            "kyc.reviewed",
            record_type="mandate",
            record_id=mandate.id,
            new_values={**values.model_dump(), "status": status.value},
        )
        if status == KycStatus.FROZEN and mandate.frozen_at is None:
            mandate.frozen_at = now
            self.audit.record(
                db,
                context,
                "mandate.frozen",
                record_type="mandate",
                record_id=mandate.id,
                new_values={"reason": "Sanctions hit"},
            )
        await db.commit()
        return await self.read(db, grant)

    async def unfreeze(self, db: AsyncSession, grant: DealGrant, values: Unfreeze, context: AuditContext) -> dict[str, Any]:
        mandate = grant.mandate
        if _blank(values.reason):
            raise ValidationError("Say why the deal is unfrozen", field="reason")
        if mandate.frozen_at is None:
            raise ValidationError("This deal is not frozen", field="reason")
        assert values.reason is not None
        mandate.frozen_at = None
        record = await self._record(db, mandate.id)
        if record is not None and record.status == KycStatus.FROZEN.value:
            # Unfreezing lifts the block, it does not approve: KYC needs a fresh review.
            record.status = KycStatus.PENDING.value
        self.audit.record(
            db,
            context,
            "mandate.unfrozen",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"reason": values.reason.strip()},
        )
        await db.commit()
        return await self.read(db, grant)

    async def create_refresh_tasks(self, db: AsyncSession, now: datetime) -> None:
        rows = (
            await db.execute(
                select(KycRecord, Mandate.code_name)
                .join(Mandate, Mandate.id == KycRecord.mandate_id)
                .where(
                    KycRecord.status == KycStatus.APPROVED.value,
                    KycRecord.approved_at <= now - KYC_VALID_FOR,
                    Mandate.closed_at.is_(None),
                    or_(KycRecord.refresh_task_for.is_(None), KycRecord.refresh_task_for != KycRecord.approved_at),
                )
            )
        ).all()
        compliance = await _users_with(db, Permission.KYC_MANAGE)
        for record, code_name in rows:
            # Compliance is not on the deal team, so the task names the code name and links no deal record.
            for user in compliance:
                db.add(
                    Task(
                        title=f"Refresh KYC for {code_name}",
                        assignee_id=user.id,
                        created_by=user.id,
                        due_date=now.date(),
                        recurrence="none",
                        created_at=now,
                    )
                )
            record.refresh_task_for = record.approved_at
        await db.commit()


async def kyc_approved(db: AsyncSession, mandate: Mandate) -> bool:
    record = (await db.execute(select(KycRecord.status).where(KycRecord.mandate_id == mandate.id))).scalar_one_or_none()
    return record == KycStatus.APPROVED.value and mandate.frozen_at is None


async def conflict_check(db: AsyncSession, mandate: Mandate, counterparty_ids: list[int], context: AuditContext) -> None:
    await ConflictService().check_new_mandate(db, mandate, counterparty_ids, context)


def install() -> None:
    """Plugs the compliance slice into mandate creation and the Preparation gate (decision 14)."""
    mandate_pipeline.set_kyc_check(kyc_approved)
    mandate_service.set_conflict_check(conflict_check)
