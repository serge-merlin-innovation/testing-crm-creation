"""The origination pipeline (ORI-01..04): opportunities before a mandate is signed.

Visibility follows the deal wall (AUTHZ-02): the role must read staffed deals, and the user must own
the opportunity or be invited to it. Anything else is a 404, so a URL never confirms an opportunity.
"""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity.models import Activity, ActivityLink
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import (
    OpportunityNotFoundError,
    PermissionDeniedError,
    ResourceExistsError,
    ValidationError,
)
from ..company.models import Company
from ..company.ports import UnconfiguredAnnualAccounts, UnconfiguredRegister
from ..company.service import CompanyService
from ..compliance.models import DealCounterparty
from ..contact.models import Employment, RelationshipHolder
from ..fee.models import FeeTerms
from ..fee.schemas import FeeTermsValues
from ..mandate.models import DealTeamMember, Mandate
from ..mandate.schemas import ConflictStatus, MandateCreate, MandateType, TeamRole
from ..mandate.service import MandateService
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..picklist.schemas import PicklistKind
from ..picklist.service import PicklistService
from ..role.authorization import has_permission
from ..role.permissions import Permission, RoleName
from ..task.models import Task
from ..user.models import User
from ..user.service import display_name
from .models import Opportunity, OpportunityCredential, OpportunityLink, OpportunityMember, OriginationSettings
from .schemas import (
    CLOSED_STAGES,
    CredentialCreate,
    LinkCreate,
    OpportunityCreate,
    OpportunityStage,
    OriginationSettingsValues,
    StageChange,
    WinRequest,
)

DEFAULT_DORMANT_DAYS = 90
# The team role each firm role takes on the mandate a won opportunity creates.
TEAM_ROLE_OF = {
    RoleName.PARTNER.value: TeamRole.PARTNER,
    RoleName.DIRECTOR.value: TeamRole.DIRECTOR,
    RoleName.ANALYST.value: TeamRole.ANALYST,
}


def _user_name(user: User) -> str:
    full = " ".join(part for part in (user.first_name, user.last_name) if part) or user.name
    return display_name(full, user.is_deleted) or full


def can_see_opportunities(user: dict[str, Any]) -> bool:
    return has_permission(user, Permission.DEALS_READ_STAFFED)


def visible(user: dict[str, Any]) -> Any:
    """The opportunities this user may read: owned or invited, with a role that reads staffed deals."""
    if not can_see_opportunities(user):
        return Opportunity.id.is_(None)
    invited = select(OpportunityMember.opportunity_id).where(OpportunityMember.user_id == user["id"])
    return or_(Opportunity.owner_id == user["id"], Opportunity.id.in_(invited))


async def has_active_mandate(db: AsyncSession, company_id: int) -> bool:
    """ORI-01 c4: the company, or any entity of its group, is client, target or counterparty of a running deal."""
    group = await CompanyService(UnconfiguredRegister(), UnconfiguredAnnualAccounts()).group_member_ids(db, company_id)
    running = (
        Mandate.closed_at.is_(None),
        Mandate.conflict_status != ConflictStatus.REJECTED.value,
    )
    as_party = select(Mandate.id).where(*running, or_(Mandate.client_id.in_(group), Mandate.target_id.in_(group)))
    as_counterparty = (
        select(Mandate.id)
        .join(DealCounterparty, DealCounterparty.mandate_id == Mandate.id)
        .where(*running, DealCounterparty.company_id.in_(group))
    )
    return (await db.execute(as_party.union(as_counterparty).limit(1))).first() is not None


class OriginationService:
    def __init__(
        self,
        notifications: NotificationService,
        audit: AuditService | None = None,
        picklists: PicklistService | None = None,
    ) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()
        self.picklists = picklists or PicklistService()

    # Access

    async def get(self, db: AsyncSession, user: dict[str, Any], opportunity_id: int) -> Opportunity:
        found = (
            await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id, visible(user)))
        ).scalar_one_or_none()
        if found is None:
            raise OpportunityNotFoundError(f"Opportunity {opportunity_id} not found")
        return found

    async def editable(self, db: AsyncSession, user: dict[str, Any], opportunity_id: int) -> Opportunity:
        opportunity = await self.get(db, user, opportunity_id)
        if not has_permission(user, Permission.DEALS_EDIT_STAFFED):
            raise PermissionDeniedError("Missing deals.edit_staffed")
        if opportunity.stage in CLOSED_STAGES:
            raise ValidationError("This opportunity is closed", field="stage")
        return opportunity

    async def owned(self, db: AsyncSession, user: dict[str, Any], opportunity_id: int) -> Opportunity:
        opportunity = await self.editable(db, user, opportunity_id)
        if opportunity.owner_id != user["id"]:
            raise PermissionDeniedError("Only the owner does this")
        return opportunity

    # Reads

    async def _rows(self, db: AsyncSession, query: Any) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                query.add_columns(Company.name, User)
                .join(Company, Company.id == Opportunity.company_id)
                .join(User, User.id == Opportunity.owner_id)
            )
        ).all()
        return [
            {
                "opportunity": opportunity,
                "company_name": company_name,
                "owner_name": _user_name(owner),
            }
            for opportunity, company_name, owner in rows
        ]

    async def _item(self, db: AsyncSession, row: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        opportunity: Opportunity = row["opportunity"]
        return {
            "id": opportunity.id,
            "company_id": opportunity.company_id,
            "company_name": row["company_name"],
            "owner_id": opportunity.owner_id,
            "owner_name": row["owner_name"],
            "type": opportunity.type,
            "trigger": opportunity.trigger,
            "estimated_ev": opportunity.estimated_ev,
            "probability": opportunity.probability,
            "sector_id": opportunity.sector_id,
            "stage": opportunity.stage,
            "stage_changed_at": opportunity.stage_changed_at,
            "created_at": opportunity.created_at,
            "lost_reason": opportunity.lost_reason,
            "competitor_advisor": opportunity.competitor_advisor,
            "revisit_date": opportunity.revisit_date,
            "mandate_id": opportunity.mandate_id,
            "conflict_warning": opportunity.stage not in CLOSED_STAGES and await has_active_mandate(db, opportunity.company_id),
            "is_owner": opportunity.owner_id == user["id"],
        }

    async def list_visible(
        self, db: AsyncSession, user: dict[str, Any], stage: OpportunityStage | None
    ) -> list[dict[str, Any]]:
        query = select(Opportunity).where(visible(user)).order_by(Opportunity.created_at.desc(), Opportunity.id.desc())
        if stage is not None:
            query = query.where(Opportunity.stage == stage.value)
        return [await self._item(db, row, user) for row in await self._rows(db, query)]

    async def read(self, db: AsyncSession, user: dict[str, Any], opportunity: Opportunity) -> dict[str, Any]:
        await db.refresh(opportunity)
        row = (await self._rows(db, select(Opportunity).where(Opportunity.id == opportunity.id)))[0]
        members = (
            await db.execute(
                select(User)
                .join(OpportunityMember, OpportunityMember.user_id == User.id)
                .where(OpportunityMember.opportunity_id == opportunity.id)
                .order_by(OpportunityMember.added_at, OpportunityMember.id)
            )
        ).scalars()
        links = (
            await db.execute(
                select(OpportunityLink).where(OpportunityLink.opportunity_id == opportunity.id).order_by(OpportunityLink.id)
            )
        ).scalars()
        credentials = (
            await db.execute(
                select(Mandate, OpportunityCredential.id)
                .join(OpportunityCredential, OpportunityCredential.mandate_id == Mandate.id)
                .where(OpportunityCredential.opportunity_id == opportunity.id)
                .order_by(OpportunityCredential.id)
            )
        ).all()
        detail = {
            **await self._item(db, row, user),
            "members": [{"user_id": m.id, "name": _user_name(m), "role_name": m.role_name} for m in members],
            "links": list(links),
            "credentials": [_credential(mandate) for mandate, _ in credentials],
        }
        if has_permission(user, Permission.FEES_READ):
            detail["fee_draft"] = opportunity.fee_draft
        return detail

    # Writes

    async def create(self, db: AsyncSession, values: OpportunityCreate, context: AuditContext) -> Opportunity:
        assert context.user_id is not None
        if await db.get(Company, values.company_id) is None:
            raise ValidationError(f"Company {values.company_id} does not exist", field="company_id")
        if values.sector_id is not None:
            await self.picklists.require_active(db, values.sector_id, PicklistKind.SECTOR)
        now = context.clock.now()
        opportunity = Opportunity(
            company_id=values.company_id,
            owner_id=context.user_id,
            type=values.type.value,
            trigger=values.trigger.value,
            estimated_ev=values.estimated_ev,
            probability=values.probability,
            stage=OpportunityStage.LEAD.value,
            created_at=now,
            stage_changed_at=now,
            sector_id=values.sector_id,
        )
        db.add(opportunity)
        await db.flush()
        self.audit.record(
            db,
            context,
            "opportunity.created",
            record_type="opportunity",
            record_id=opportunity.id,
            new_values=values.model_dump(mode="json"),
        )
        await db.commit()
        return opportunity

    async def change_stage(
        self, db: AsyncSession, opportunity: Opportunity, values: StageChange, context: AuditContext
    ) -> None:
        stage = values.stage
        if stage == OpportunityStage.WON:
            raise ValidationError("Confirm Won to create the mandate", field="stage")
        opportunity.lost_reason = None
        opportunity.competitor_advisor = None
        if stage == OpportunityStage.LOST:
            if values.lost_reason is None:
                raise ValidationError("Say why the opportunity was lost", field="lost_reason")
            opportunity.lost_reason = values.lost_reason.value
            advisor = (values.competitor_advisor or "").strip()
            opportunity.competitor_advisor = advisor or None
        if stage == OpportunityStage.ON_HOLD:
            if values.revisit_date is None:
                raise ValidationError("Give the date to revisit this opportunity", field="revisit_date")
            opportunity.revisit_date = values.revisit_date
            opportunity.revisit_tasked_at = None
        else:
            opportunity.revisit_date = None
        old = opportunity.stage
        opportunity.stage = stage.value
        opportunity.stage_changed_at = context.clock.now()
        self.audit.record(
            db,
            context,
            "opportunity.stage_changed",
            record_type="opportunity",
            record_id=opportunity.id,
            old_values={"stage": old},
            new_values=values.model_dump(mode="json"),
        )
        await db.commit()

    async def add_member(self, db: AsyncSession, opportunity: Opportunity, user_id: int, context: AuditContext) -> None:
        assert context.user_id is not None
        user = await db.get(User, user_id)
        if user is None or user.is_deleted or user.role_id is None:
            raise ValidationError("This user does not exist or has no role", field="user_id")
        if user.id == opportunity.owner_id:
            raise ResourceExistsError("The owner already sees it")
        exists = (
            await db.execute(
                select(OpportunityMember.id).where(
                    OpportunityMember.opportunity_id == opportunity.id, OpportunityMember.user_id == user.id
                )
            )
        ).first()
        if exists is not None:
            raise ResourceExistsError("Already invited")
        now = context.clock.now()
        db.add(OpportunityMember(opportunity_id=opportunity.id, user_id=user.id, added_by=context.user_id, added_at=now))
        self.audit.record(
            db,
            context,
            "opportunity.member_added",
            record_type="opportunity",
            record_id=opportunity.id,
            new_values={"user_id": user.id},
        )
        await self.notifications.add(
            db,
            Message(
                user_id=user.id,
                email=user.email,
                kind=EventKind.OPPORTUNITY_INVITED.value,
                title="You were invited to an opportunity",
                body="A colleague shared an origination opportunity with you.",
                link=f"/origination/{opportunity.id}",
            ),
            now,
        )
        await db.commit()
        await self.notifications.flush_emails()

    async def candidates(self, db: AsyncSession, opportunity: Opportunity) -> list[dict[str, Any]]:
        """Colleagues who can be invited: active, with a role that reads staffed deals."""
        invited = select(OpportunityMember.user_id).where(OpportunityMember.opportunity_id == opportunity.id)
        users = (
            await db.execute(
                select(User)
                .where(
                    User.is_deleted.is_(False),
                    User.role_id.is_not(None),
                    User.id != opportunity.owner_id,
                    User.id.not_in(invited),
                )
                .order_by(User.name)
            )
        ).scalars()
        return [
            {"user_id": user.id, "name": _user_name(user), "role_name": user.role_name}
            for user in users
            if Permission.DEALS_READ_STAFFED.value in (user.permissions or [])
        ]

    async def remove_member(self, db: AsyncSession, opportunity: Opportunity, user_id: int, context: AuditContext) -> None:
        member = (
            await db.execute(
                select(OpportunityMember).where(
                    OpportunityMember.opportunity_id == opportunity.id, OpportunityMember.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise OpportunityNotFoundError("Not invited")
        await db.delete(member)
        self.audit.record(
            db,
            context,
            "opportunity.member_removed",
            record_type="opportunity",
            record_id=opportunity.id,
            old_values={"user_id": user_id},
        )
        await db.commit()

    async def add_link(
        self, db: AsyncSession, opportunity: Opportunity, values: LinkCreate, context: AuditContext
    ) -> OpportunityLink:
        assert context.user_id is not None
        link = OpportunityLink(
            opportunity_id=opportunity.id,
            label=values.label.strip(),
            url=values.url,
            added_by=context.user_id,
            added_at=context.clock.now(),
        )
        db.add(link)
        await db.commit()
        return link

    async def remove_link(self, db: AsyncSession, opportunity: Opportunity, link_id: int, context: AuditContext) -> None:
        link = await db.get(OpportunityLink, link_id)
        if link is None or link.opportunity_id != opportunity.id:
            raise OpportunityNotFoundError("Link not found")
        self.audit.record(
            db,
            context,
            "opportunity.link_removed",
            record_type="opportunity",
            record_id=opportunity.id,
            old_values={"label": link.label, "url": link.url},
        )
        await db.delete(link)
        await db.commit()

    async def add_credential(
        self, db: AsyncSession, opportunity: Opportunity, values: CredentialCreate, context: AuditContext
    ) -> dict[str, Any]:
        assert context.user_id is not None
        mandate = (
            await db.execute(select(Mandate).where(Mandate.id == values.mandate_id, *_public_credential()))
        ).scalar_one_or_none()
        if mandate is None:
            raise ValidationError("Only closed deals with a tombstone allowed can be credentials", field="mandate_id")
        exists = (
            await db.execute(
                select(OpportunityCredential.id).where(
                    OpportunityCredential.opportunity_id == opportunity.id, OpportunityCredential.mandate_id == mandate.id
                )
            )
        ).first()
        if exists is None:
            db.add(
                OpportunityCredential(
                    opportunity_id=opportunity.id, mandate_id=mandate.id, added_by=context.user_id, added_at=context.clock.now()
                )
            )
            await db.commit()
        return _credential(mandate)

    async def remove_credential(
        self, db: AsyncSession, opportunity: Opportunity, mandate_id: int, context: AuditContext
    ) -> None:
        row = (
            await db.execute(
                select(OpportunityCredential).where(
                    OpportunityCredential.opportunity_id == opportunity.id, OpportunityCredential.mandate_id == mandate_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise OpportunityNotFoundError("Credential not found")
        self.audit.record(
            db,
            context,
            "opportunity.credential_removed",
            record_type="opportunity",
            record_id=opportunity.id,
            old_values={"mandate_id": mandate_id},
        )
        await db.delete(row)
        await db.commit()

    async def search_credentials(
        self, db: AsyncSession, sector_id: int | None, ev_min: Any, ev_max: Any, q: str | None
    ) -> list[dict[str, Any]]:
        query = select(Mandate).where(*_public_credential()).order_by(Mandate.closing_date.desc(), Mandate.id.desc())
        if sector_id is not None:
            query = query.where(Mandate.sector_id == sector_id)
        if ev_min is not None:
            query = query.where(Mandate.final_ev >= ev_min)
        if ev_max is not None:
            query = query.where(Mandate.final_ev <= ev_max)
        if q:
            query = query.where(Mandate.code_name_key.contains(q.strip().lower()))
        return [_credential(mandate) for mandate in (await db.execute(query.limit(200))).scalars()]

    async def save_fee_draft(
        self, db: AsyncSession, opportunity: Opportunity, values: FeeTermsValues, context: AuditContext
    ) -> dict[str, Any] | None:
        draft = values.model_dump(mode="json", exclude={"change_reason", "amended_letter_url"})
        opportunity.fee_draft = draft
        # Fee history stays out of the opportunity's audit trail, like the deal's (AUTHZ-06).
        self.audit.record(
            db, context, "fee.draft_set", record_type="opportunity_fee_draft", record_id=opportunity.id, new_values=draft
        )
        await db.commit()
        return draft

    async def win(self, db: AsyncSession, opportunity: Opportunity, values: WinRequest, context: AuditContext) -> Mandate:
        """ORI-03 c1: a mandate with company, team and fee draft copied, through the conflict check (AUTHZ-05)."""
        if opportunity.mandate_id is not None:
            raise ResourceExistsError("Already won")
        sector_id = values.sector_id or opportunity.sector_id
        if sector_id is None:
            raise ValidationError("Choose the mandate's sector", field="sector_id")
        fee_draft = FeeTermsValues.model_validate(opportunity.fee_draft) if opportunity.fee_draft else None
        mandates = MandateService(self.notifications, self.audit, self.picklists)
        created = await mandates.create(
            db,
            MandateCreate(
                code_name=values.code_name,
                client_id=opportunity.company_id,
                type=MandateType(opportunity.type),
                sector_id=sector_id,
                lead_partner_id=opportunity.owner_id,
                estimated_ev=opportunity.estimated_ev,
                target_id=values.target_id,
            ),
            context,
        )
        mandate = await db.get(Mandate, created["id"])
        assert mandate is not None
        assert context.user_id is not None
        now = context.clock.now()
        staffed = set(
            (await db.execute(select(DealTeamMember.user_id).where(DealTeamMember.mandate_id == mandate.id))).scalars()
        )
        invited = (
            await db.execute(
                select(User)
                .join(OpportunityMember, OpportunityMember.user_id == User.id)
                .where(OpportunityMember.opportunity_id == opportunity.id, User.is_deleted.is_(False))
                .order_by(OpportunityMember.id)
            )
        ).scalars()
        for user in invited:
            if user.id in staffed:
                continue
            role = TEAM_ROLE_OF.get(user.role_name or "", TeamRole.OTHER)
            await mandates._staff(db, mandate, user, role, context.user_id, now, None, context)
        if fee_draft is not None:
            db.add(
                FeeTerms(
                    mandate_id=mandate.id,
                    retainer_monthly=fee_draft.retainer_monthly,
                    success_fee_kind=fee_draft.success_fee_kind.value,
                    minimum_fee=fee_draft.minimum_fee,
                    retainers_creditable=fee_draft.retainers_creditable,
                    updated_by=context.user_id,
                    updated_at=now,
                    success_fee_percent=fee_draft.success_fee_percent,
                    success_fee_fixed=fee_draft.success_fee_fixed,
                    lehman_tiers=[tier.model_dump(mode="json") for tier in fee_draft.lehman_tiers],
                )
            )
            self.audit.record(
                db, context, "fee.set", record_type="fee_terms", record_id=mandate.id, new_values=opportunity.fee_draft
            )
        old = opportunity.stage
        opportunity.stage = OpportunityStage.WON.value
        opportunity.stage_changed_at = now
        opportunity.mandate_id = mandate.id
        opportunity.revisit_date = None
        self.audit.record(
            db,
            context,
            "opportunity.won",
            record_type="opportunity",
            record_id=opportunity.id,
            old_values={"stage": old},
            new_values={"stage": opportunity.stage, "mandate_id": mandate.id},
        )
        await db.commit()
        await self.notifications.flush_emails()
        return mandate

    # Settings

    async def settings(self, db: AsyncSession) -> OriginationSettings:
        row = await db.get(OriginationSettings, 1)
        if row is None:
            row = OriginationSettings(id=1, dormant_days=DEFAULT_DORMANT_DAYS)
            db.add(row)
            await db.flush()
        return row

    async def update_settings(
        self, db: AsyncSession, values: OriginationSettingsValues, context: AuditContext
    ) -> OriginationSettings:
        row = await self.settings(db)
        old = row.dormant_days
        row.dormant_days = values.dormant_days
        self.audit.record(
            db,
            context,
            "origination.settings_changed",
            record_type="origination_settings",
            record_id=1,
            old_values={"dormant_days": old},
            new_values={"dormant_days": values.dormant_days},
        )
        await db.commit()
        return row

    # Reminders (ORI-03 c3, ORI-04)

    async def create_revisit_tasks(self, db: AsyncSession, now: datetime) -> None:
        due = (
            await db.execute(
                select(Opportunity, Company.name)
                .join(Company, Company.id == Opportunity.company_id)
                .where(
                    Opportunity.stage == OpportunityStage.ON_HOLD.value,
                    Opportunity.revisit_date <= now.date(),
                    Opportunity.revisit_tasked_at.is_(None),
                )
            )
        ).all()
        for opportunity, company_name in due:
            assert opportunity.revisit_date is not None
            await self._task(db, opportunity, f"Revisit the opportunity on {company_name}", opportunity.revisit_date, now)
            opportunity.revisit_tasked_at = now
        await db.commit()
        await self.notifications.flush_emails()

    async def create_dormant_tasks(self, db: AsyncSession, now: datetime) -> None:
        threshold = timedelta(days=(await self.settings(db)).dormant_days)
        prospects = (
            await db.execute(
                select(Opportunity, Company.name)
                .join(Company, Company.id == Opportunity.company_id)
                .where(Opportunity.stage.not_in(CLOSED_STAGES))
            )
        ).all()
        for opportunity, company_name in prospects:
            last = max(
                moment
                for moment in (
                    opportunity.created_at,
                    opportunity.dormant_tasked_at,
                    await last_activity(db, opportunity.company_id),
                )
                if moment is not None
            )
            if now - last < threshold:
                continue
            holder = await relationship_holder(db, opportunity.company_id)
            await self._task(db, opportunity, f"Reconnect with {company_name}", now.date(), now, holder)
            opportunity.dormant_tasked_at = now
        await db.commit()
        await self.notifications.flush_emails()

    async def _task(
        self,
        db: AsyncSession,
        opportunity: Opportunity,
        title: str,
        due: date,
        now: datetime,
        assignee_id: int | None = None,
    ) -> None:
        owner = await db.get(User, assignee_id or opportunity.owner_id)
        if owner is None or owner.is_deleted:
            return
        db.add(
            Task(
                title=title,
                assignee_id=owner.id,
                created_by=owner.id,
                due_date=due,
                recurrence="none",
                created_at=now,
                record_type="company",
                record_id=opportunity.company_id,
            )
        )
        await self.notifications.add(
            db,
            Message(
                user_id=owner.id,
                email=owner.email,
                kind=EventKind.TASK_ASSIGNED.value,
                title=title,
                body=f"{title}, due {due.isoformat()}.",
                link=f"/origination/{opportunity.id}",
            ),
            now,
        )


async def relationship_holder(db: AsyncSession, company_id: int) -> int | None:
    """The colleague with the strongest CON-02 relationship to someone currently working at the company."""
    contacts = select(Employment.contact_id).where(Employment.company_id == company_id, Employment.end_date.is_(None))
    return (
        await db.execute(
            select(RelationshipHolder.user_id)
            .join(User, User.id == RelationshipHolder.user_id)
            .where(RelationshipHolder.contact_id.in_(contacts), User.is_deleted.is_(False))
            .order_by(RelationshipHolder.strength.desc(), RelationshipHolder.user_id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def last_activity(db: AsyncSession, company_id: int) -> datetime | None:
    """The latest activity on the company or on anyone currently working there."""
    contacts = select(Employment.contact_id).where(Employment.company_id == company_id, Employment.end_date.is_(None))
    return (
        await db.execute(
            select(func.max(Activity.occurred_at))
            .join(ActivityLink, ActivityLink.activity_id == Activity.id)
            .where(
                Activity.deleted_at.is_(None),
                or_(
                    (ActivityLink.record_type == "company") & (ActivityLink.record_id == company_id),
                    (ActivityLink.record_type == "contact") & (ActivityLink.record_id.in_(contacts)),
                ),
            )
        )
    ).scalar_one_or_none()


def _public_credential() -> tuple[Any, ...]:
    return (Mandate.stage == "closed_won", Mandate.tombstone_allowed.is_(True), Mandate.closed_at.is_not(None))


def _credential(mandate: Mandate) -> dict[str, Any]:
    return {
        "id": mandate.id,
        "code_name": mandate.code_name,
        "type": mandate.type,
        "sector_id": mandate.sector_id,
        "ev": mandate.final_ev,
        "closing_date": mandate.closing_date,
    }
