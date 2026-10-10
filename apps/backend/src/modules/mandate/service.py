import csv
import io
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..audit.models import AuditEntry
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import (
    DealLinkNotFoundError,
    LastLeadPartnerError,
    MandateExistsError,
    TeamMemberExistsError,
    TeamMemberNotFoundError,
    ValidationError,
)
from ..common.spreadsheet import safe_row
from ..company.models import Company
from ..company.service import normalize_name
from ..notification.service import Message, NotificationService
from ..picklist.schemas import PicklistKind
from ..picklist.service import PicklistService
from ..role.permissions import RoleName
from ..user.models import User
from ..user.service import display_name
from .models import DealLink, DealTeamMember, Mandate, WallCrossing
from .policy import DealGrant, DealPolicy
from .schemas import (
    ConflictStatus,
    DealFilters,
    DealLinkCreate,
    HistoryEntry,
    MandateCreate,
    MandateListItem,
    MandateRead,
    MandateType,
    MandateUpdate,
    OutcomeRead,
    TeamMemberCreate,
    TeamMemberRead,
    TeamRole,
    UserOption,
    WallCrossingRead,
)
from .stages import DealStage, stages_for

# Words that say nothing about who the company is, so a code name may contain them.
GENERIC_NAME_WORDS = {"holding", "holdings", "group", "groep", "groupe", "company", "international", "the", "and", "de", "et"}
TRACKED_FIELDS = ("code_name", "client_id", "target_id", "type", "sector_id", "lead_partner_id", "estimated_ev", "stage")


# The conflict check (AUTHZ-05) lives in the compliance slice, which plugs in through
# `set_conflict_check`. It runs inside the creating transaction, so a deal is never saved unchecked.
ConflictCheck = Callable[[AsyncSession, Mandate, list[int], AuditContext], Awaitable[None]]


async def no_conflict_check(db: AsyncSession, mandate: Mandate, counterparty_ids: list[int], context: AuditContext) -> None:
    return None


_conflict_check: ConflictCheck = no_conflict_check


def set_conflict_check(check: ConflictCheck) -> None:
    global _conflict_check
    _conflict_check = check


class StaleVersionError(Exception):
    def __init__(self, current: dict[str, Any]) -> None:
        super().__init__("The deal changed since you opened it")
        self.current = current


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return value


def _snapshot(mandate: Mandate) -> dict[str, Any]:
    return {field: _value(getattr(mandate, field)) for field in TRACKED_FIELDS}


def _words(text: str) -> list[str]:
    return normalize_name(text).split()


def code_name_reveals(code_name: str, company_name: str) -> bool:
    """True when the code name contains the company's name, or a distinctive word of it."""
    code = f" {' '.join(_words(code_name))} "
    name_words = _words(company_name)
    if name_words and f" {' '.join(name_words)} " in code:
        return True
    return any(f" {word} " in code for word in name_words if len(word) >= 3 and word not in GENERIC_NAME_WORDS)


class MandateService:
    def __init__(
        self,
        notifications: NotificationService,
        audit: AuditService | None = None,
        picklists: PicklistService | None = None,
    ) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()
        self.picklists = picklists or PicklistService()

    async def _company(self, db: AsyncSession, company_id: int, field: str) -> Company:
        company = await db.get(Company, company_id)
        if company is None:
            raise ValidationError(f"Company {company_id} does not exist", field=field)
        return company

    async def _user(self, db: AsyncSession, user_id: int, field: str = "user_id") -> User:
        user = await db.get(User, user_id)
        if user is None or user.is_deleted or user.role_id is None:
            raise ValidationError("This user does not exist or has no role", field=field)
        return user

    async def _check_code_name(
        self, db: AsyncSession, code_name: str, companies: list[Company], exclude_id: int | None
    ) -> None:
        for company in companies:
            if code_name_reveals(code_name, company.name):
                raise ValidationError("The code name must not contain the client or target name", field="code_name")
        query = select(Mandate.id).where(Mandate.code_name_key == code_name.strip().lower())
        if exclude_id is not None:
            query = query.where(Mandate.id != exclude_id)
        if (await db.execute(query)).first() is not None:
            raise MandateExistsError("Code name in use")

    async def _require_partner(self, db: AsyncSession, user_id: int, field: str) -> User:
        user = await self._user(db, user_id, field)
        if user.role_name != RoleName.PARTNER.value:
            raise ValidationError("The lead partner must hold the Partner role", field=field)
        return user

    async def record_view(self, db: AsyncSession, grant: DealGrant, context: AuditContext) -> None:
        """AUD-01 c1: who opened which deal, from where. Break-glass reads are flagged."""
        self.audit.record(
            db,
            context,
            "mandate.viewed",
            record_type="mandate",
            record_id=grant.mandate.id,
            new_values={"break_glass": True} if grant.emergency else None,
        )
        await db.commit()

    async def read(self, db: AsyncSession, mandate: Mandate, grant: DealGrant | None) -> dict[str, Any]:
        client = await db.get(Company, mandate.client_id)
        target = await db.get(Company, mandate.target_id) if mandate.target_id else None
        lead = await db.get(User, mandate.lead_partner_id)
        assert client is not None
        assert lead is not None
        return MandateRead(
            id=mandate.id,
            code_name=mandate.code_name,
            type=MandateType(mandate.type),
            stage=DealStage(mandate.stage),
            lead_partner_id=mandate.lead_partner_id,
            lead_partner_name=lead.name,
            client_id=mandate.client_id,
            client_name=client.name,
            target_id=mandate.target_id,
            target_name=target.name if target else None,
            sector_id=mandate.sector_id,
            estimated_ev=mandate.estimated_ev,
            stages=list(stages_for(mandate.type)),
            version=mandate.version,
            created_at=mandate.created_at,
            updated_at=mandate.updated_at,
            stage_changed_at=mandate.stage_changed_at,
            closed_at=mandate.closed_at,
            outcome=OutcomeRead(
                final_ev=mandate.final_ev,
                buyer=mandate.buyer,
                ev_ebitda=mandate.ev_ebitda,
                closing_date=mandate.closing_date,
                tombstone_allowed=mandate.tombstone_allowed,
                abort_reason=mandate.abort_reason,
            ),
            can_edit=grant is None or grant.can_edit,
            can_manage_team=grant is None or grant.can_manage_team,
            can_close=grant is None or (grant.is_closer and not grant.is_closed),
            can_reopen=grant is not None and grant.is_closer and grant.is_closed,
            conflict_status=ConflictStatus(mandate.conflict_status),
            frozen=mandate.frozen_at is not None,
        ).model_dump(mode="json")

    def _deal_message(self, mandate: Mandate, user: User, kind: str, title: str, body: str) -> Message:
        return Message(
            user_id=user.id,
            email=user.email,
            kind=kind,
            title=title,
            body=body,
            link=f"/deals/{mandate.id}",
            mandate_id=mandate.id,
        )

    async def create(self, db: AsyncSession, values: MandateCreate, context: AuditContext) -> dict[str, Any]:
        assert context.user_id is not None
        client = await self._company(db, values.client_id, "client_id")
        companies = [client]
        if values.target_id is not None:
            companies.append(await self._company(db, values.target_id, "target_id"))
        await self.picklists.require_active(db, values.sector_id, PicklistKind.SECTOR)
        lead = await self._require_partner(db, values.lead_partner_id, "lead_partner_id")
        await self._check_code_name(db, values.code_name, companies, None)

        now = context.clock.now()
        mandate = Mandate(
            code_name=values.code_name.strip(),
            code_name_key=values.code_name.strip().lower(),
            client_id=values.client_id,
            type=values.type.value,
            sector_id=values.sector_id,
            lead_partner_id=values.lead_partner_id,
            estimated_ev=values.estimated_ev,
            stage=stages_for(values.type.value)[0].value,
            stage_changed_at=now,
            created_at=now,
            updated_at=now,
            target_id=values.target_id,
            created_by=context.user_id,
        )
        db.add(mandate)
        try:
            await db.flush()
        except IntegrityError as error:
            await db.rollback()
            raise MandateExistsError("Code name in use") from error

        await self._staff(db, mandate, lead, TeamRole.LEAD_PARTNER, context.user_id, now, None, context)
        if context.user_id != lead.id:
            creator = await self._user(db, context.user_id)
            await self._staff(db, mandate, creator, TeamRole.PARTNER, context.user_id, now, None, context)
        self.audit.record(
            db, context, "mandate.created", record_type="mandate", record_id=mandate.id, new_values=_snapshot(mandate)
        )
        await _conflict_check(db, mandate, values.counterparty_ids, context)
        await db.commit()
        await self.notifications.flush_emails()
        return await self.read(db, mandate, None)

    async def _staff(
        self,
        db: AsyncSession,
        mandate: Mandate,
        user: User,
        role: TeamRole,
        by_user_id: int,
        now: datetime,
        expires_at: datetime | None,
        context: AuditContext,
    ) -> None:
        db.add(
            DealTeamMember(
                mandate_id=mandate.id,
                user_id=user.id,
                role=role.value,
                added_by=by_user_id,
                added_at=now,
                expires_at=expires_at,
            )
        )
        db.add(
            WallCrossing(
                mandate_id=mandate.id,
                user_id=user.id,
                by_user_id=by_user_id,
                action="added",
                role=role.value,
                at=now,
                expires_at=expires_at,
            )
        )
        self.audit.record(
            db,
            context,
            "deal_team.added",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"user_id": user.id, "role": role.value, "expires_at": expires_at.isoformat() if expires_at else None},
        )
        if user.id != by_user_id:
            await self.notifications.add(
                db,
                self._deal_message(
                    mandate,
                    user,
                    "deal_team.added",
                    f"You were added to the deal team of {mandate.code_name}",
                    f"You now have access to {mandate.code_name} as {role.value.replace('_', ' ')}.",
                ),
                now,
            )

    async def list_visible(
        self, db: AsyncSession, user: dict[str, Any], now: datetime, q: str | None, filters: DealFilters | None = None
    ) -> list[dict[str, Any]]:
        query = (
            DealPolicy(now)
            .visible(user, select(Mandate, User.name).join(User, User.id == Mandate.lead_partner_id))
            .order_by(Mandate.code_name)
        )
        if q:
            query = query.where(Mandate.code_name_key.contains(q.strip().lower(), autoescape=True))
        if filters is not None:
            if filters.partner_id is not None:
                partnered = select(DealTeamMember.mandate_id).where(
                    DealTeamMember.user_id == filters.partner_id,
                    DealTeamMember.role.in_([TeamRole.LEAD_PARTNER.value, TeamRole.PARTNER.value]),
                )
                query = query.where(Mandate.id.in_(partnered))
            if filters.type is not None:
                query = query.where(Mandate.type == filters.type.value)
            if filters.sector_id is not None:
                query = query.where(Mandate.sector_id == filters.sector_id)
            if filters.stage is not None:
                query = query.where(Mandate.stage == filters.stage.value)
        return [
            MandateListItem(
                id=mandate.id,
                code_name=mandate.code_name,
                type=MandateType(mandate.type),
                stage=DealStage(mandate.stage),
                lead_partner_id=mandate.lead_partner_id,
                lead_partner_name=lead_name,
                sector_id=mandate.sector_id,
                estimated_ev=mandate.estimated_ev,
                stage_changed_at=mandate.stage_changed_at,
                closed_at=mandate.closed_at,
            ).model_dump(mode="json")
            for mandate, lead_name in (await db.execute(query)).all()
        ]

    async def update(self, db: AsyncSession, grant: DealGrant, values: MandateUpdate, context: AuditContext) -> dict[str, Any]:
        mandate = grant.mandate
        await db.refresh(mandate, with_for_update=True)
        if values.version != mandate.version:
            current = await self.read(db, mandate, grant)
            await db.rollback()
            raise StaleVersionError(current)

        changes = values.model_dump(mode="python", exclude_unset=True, exclude={"version"})
        for required in ("code_name", "client_id", "type", "sector_id", "estimated_ev"):
            if required in changes and changes[required] is None:
                raise ValidationError(f"{required} is required", field=required)
        if "sector_id" in changes:
            await self.picklists.require_active(db, changes["sector_id"], PicklistKind.SECTOR)
        client_id = changes.get("client_id", mandate.client_id)
        target_id = changes.get("target_id", mandate.target_id)
        companies = [await self._company(db, client_id, "client_id")]
        if target_id is not None:
            companies.append(await self._company(db, target_id, "target_id"))
        code_name = (changes.get("code_name") or mandate.code_name).strip()
        await self._check_code_name(db, code_name, companies, mandate.id)

        old = _snapshot(mandate)
        for key, value in changes.items():
            if key == "type" and value is not None:
                value = value.value
            if key == "code_name":
                value = value.strip()
                mandate.code_name_key = value.lower()
            setattr(mandate, key, value)
        if "estimated_ev" in changes:
            mandate.estimated_ev = Decimal(changes["estimated_ev"]).quantize(Decimal("0.01"))
        new = _snapshot(mandate)
        changed = {key for key in TRACKED_FIELDS if old[key] != new[key]}
        if changed:
            mandate.version += 1
            mandate.updated_at = context.clock.now()
            self.audit.record(
                db,
                context,
                "mandate.updated",
                record_type="mandate",
                record_id=mandate.id,
                old_values={key: old[key] for key in changed},
                new_values={key: new[key] for key in changed},
            )
        await db.commit()
        return await self.read(db, mandate, grant)

    async def history(self, db: AsyncSession, mandate_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(AuditEntry, User.name, User.is_deleted)
                .outerjoin(User, User.id == AuditEntry.user_id)
                .where(
                    AuditEntry.record_type == "mandate",
                    AuditEntry.record_id == str(mandate_id),
                    AuditEntry.action != "mandate.viewed",
                )
                .order_by(AuditEntry.created_at.desc(), AuditEntry.id.desc())
            )
        ).all()
        entries: list[dict[str, Any]] = []
        for entry, user_name, inactive in rows:
            base = {
                "action": entry.action,
                "at": entry.created_at,
                "user_id": entry.user_id,
                "user_name": display_name(user_name, inactive),
            }
            if entry.action == "mandate.updated":
                old, new = entry.old_values or {}, entry.new_values or {}
                for field in sorted(set(old) | set(new)):
                    entries.append(
                        HistoryEntry(
                            **base, field=field, old_value=_text(old.get(field)), new_value=_text(new.get(field))
                        ).model_dump(mode="json")
                    )
            else:
                summary = entry.new_values or entry.old_values or {}
                entries.append(
                    HistoryEntry(**base, field=None, old_value=None, new_value=_text(summary) if summary else None).model_dump(
                        mode="json"
                    )
                )
        return entries

    async def team(self, db: AsyncSession, grant: DealGrant, now: datetime) -> dict[str, Any]:
        adder = aliased(User)
        rows = (
            await db.execute(
                select(DealTeamMember, User, adder.name)
                .join(User, User.id == DealTeamMember.user_id)
                .join(adder, adder.id == DealTeamMember.added_by)
                .where(DealTeamMember.mandate_id == grant.mandate.id)
                .order_by(DealTeamMember.added_at, DealTeamMember.id)
            )
        ).all()
        members = [
            TeamMemberRead(
                user_id=user.id,
                name=user.name,
                email=user.email,
                role=member.role,
                added_by=member.added_by,
                added_by_name=added_by_name,
                added_at=member.added_at,
                expires_at=member.expires_at,
            ).model_dump(mode="json")
            for member, user, added_by_name in rows
            if member.expires_at is None or member.expires_at > now
        ]
        return {"can_manage": grant.can_manage_team, "members": members}

    async def export_csv(self, db: AsyncSession, grant: DealGrant, now: datetime, context: AuditContext) -> str:
        deal = await self.read(db, grant.mandate, grant)
        team = await self.team(db, grant, now)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(safe_row(["field", "value"]))
        for field in ("code_name", "type", "stage", "lead_partner_name", "client_name", "target_name", "estimated_ev"):
            writer.writerow(safe_row([field, deal[field] if deal[field] is not None else ""]))
        writer.writerow(safe_row([]))
        writer.writerow(safe_row(["team_member", "role", "expires_at"]))
        for member in team["members"]:
            writer.writerow(safe_row([member["name"], member["role"], member["expires_at"] or ""]))
        self.audit.record(
            db, context, "export", record_type="mandate", record_id=grant.mandate.id, new_values={"format": "csv"}
        )
        await db.commit()
        return buffer.getvalue()

    async def candidates(self, db: AsyncSession, grant: DealGrant) -> list[dict[str, Any]]:
        staffed = select(DealTeamMember.user_id).where(DealTeamMember.mandate_id == grant.mandate.id)
        users = (
            await db.execute(
                select(User)
                .where(User.is_deleted.is_(False), User.role_id.is_not(None), User.id.not_in(staffed))
                .order_by(User.name)
            )
        ).scalars()
        return [UserOption(id=u.id, name=u.name, email=u.email, role_name=u.role_name).model_dump() for u in users]

    async def lead_partners(self, db: AsyncSession) -> list[dict[str, Any]]:
        users = (
            await db.execute(select(User).where(User.is_deleted.is_(False), User.role_id.is_not(None)).order_by(User.name))
        ).scalars()
        return [
            UserOption(id=u.id, name=u.name, email=u.email, role_name=u.role_name).model_dump()
            for u in users
            if u.role_name == RoleName.PARTNER.value
        ]

    async def add_member(
        self, db: AsyncSession, grant: DealGrant, values: TeamMemberCreate, context: AuditContext
    ) -> dict[str, Any]:
        assert context.user_id is not None
        mandate = grant.mandate
        user = await self._user(db, values.user_id)
        if values.role == TeamRole.LEAD_PARTNER and user.role_name != RoleName.PARTNER.value:
            raise ValidationError("A lead partner must hold the Partner role", field="role")
        existing = (
            await db.execute(
                select(DealTeamMember).where(DealTeamMember.mandate_id == mandate.id, DealTeamMember.user_id == user.id)
            )
        ).scalar_one_or_none()
        now = context.clock.now()
        if existing is not None:
            if existing.expires_at is None or existing.expires_at > now:
                raise TeamMemberExistsError("Already on the team")
            await db.delete(existing)
            await db.flush()
        await self._staff(db, mandate, user, values.role, context.user_id, now, values.expires_at, context)
        await db.commit()
        await self.notifications.flush_emails()
        team = await self.team(db, grant, now)
        return next(member for member in team["members"] if member["user_id"] == user.id)

    async def staff_until(
        self, db: AsyncSession, mandate: Mandate, user_id: int, role: TeamRole, expires_at: datetime, context: AuditContext
    ) -> None:
        """Brings a user over the wall until `expires_at` (AUTHZ-04). The caller commits."""
        assert context.user_id is not None
        user = await self._user(db, user_id)
        existing = (
            await db.execute(
                select(DealTeamMember).where(DealTeamMember.mandate_id == mandate.id, DealTeamMember.user_id == user.id)
            )
        ).scalar_one_or_none()
        now = context.clock.now()
        if existing is not None:
            if existing.expires_at is None or existing.expires_at > now:
                raise TeamMemberExistsError("Already on the team")
            await db.delete(existing)
            await db.flush()
        await self._staff(db, mandate, user, role, context.user_id, now, expires_at, context)

    async def remove_member(self, db: AsyncSession, grant: DealGrant, user_id: int, context: AuditContext) -> None:
        await self.remove_from(db, grant.mandate, user_id, context)
        await db.commit()

    async def remove_from(self, db: AsyncSession, mandate: Mandate, user_id: int, context: AuditContext) -> None:
        """Takes a user off the wall. The caller commits."""
        assert context.user_id is not None
        member = (
            await db.execute(
                select(DealTeamMember).where(DealTeamMember.mandate_id == mandate.id, DealTeamMember.user_id == user_id)
            )
        ).scalar_one_or_none()
        if member is None:
            raise TeamMemberNotFoundError("Not on the team")
        if member.role == TeamRole.LEAD_PARTNER.value:
            leads = (
                (
                    await db.execute(
                        select(DealTeamMember.user_id).where(
                            DealTeamMember.mandate_id == mandate.id,
                            DealTeamMember.role == TeamRole.LEAD_PARTNER.value,
                            DealTeamMember.user_id != user_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not leads:
                raise LastLeadPartnerError("Every deal needs one lead partner")
            if mandate.lead_partner_id == user_id:
                mandate.lead_partner_id = leads[0]
                mandate.version += 1
        now = context.clock.now()
        await db.delete(member)
        db.add(
            WallCrossing(
                mandate_id=mandate.id, user_id=user_id, by_user_id=context.user_id, action="removed", role=member.role, at=now
            )
        )
        self.audit.record(
            db,
            context,
            "deal_team.removed",
            record_type="mandate",
            record_id=mandate.id,
            old_values={"user_id": user_id, "role": member.role},
        )

    async def wall_crossings(self, db: AsyncSession, mandate_id: int) -> list[dict[str, Any]]:
        subject, actor = aliased(User), aliased(User)
        rows = (
            await db.execute(
                select(WallCrossing, subject.name, subject.is_deleted, actor.name, actor.is_deleted)
                .join(subject, subject.id == WallCrossing.user_id)
                .join(actor, actor.id == WallCrossing.by_user_id)
                .where(WallCrossing.mandate_id == mandate_id)
                .order_by(WallCrossing.at, WallCrossing.id)
            )
        ).all()
        return [
            WallCrossingRead(
                action=row.action,
                user_id=row.user_id,
                user_name=display_name(user_name, user_gone) or "",
                by_user_id=row.by_user_id,
                by_user_name=display_name(by_name, by_gone) or "",
                role=row.role,
                at=row.at,
                expires_at=row.expires_at,
            ).model_dump(mode="json")
            for row, user_name, user_gone, by_name, by_gone in rows
        ]

    async def links(self, db: AsyncSession, mandate_id: int) -> list[DealLink]:
        query = select(DealLink).where(DealLink.mandate_id == mandate_id).order_by(DealLink.label, DealLink.id)
        return list((await db.execute(query)).scalars())

    async def add_link(self, db: AsyncSession, grant: DealGrant, values: DealLinkCreate, context: AuditContext) -> DealLink:
        assert context.user_id is not None
        link = DealLink(
            mandate_id=grant.mandate.id,
            label=values.label.strip(),
            url=values.url,
            added_by=context.user_id,
            added_at=context.clock.now(),
        )
        db.add(link)
        await db.flush()
        self.audit.record(
            db,
            context,
            "deal_link.added",
            record_type="mandate",
            record_id=grant.mandate.id,
            new_values={"label": link.label, "url": link.url},
        )
        await db.commit()
        return link

    async def remove_link(self, db: AsyncSession, grant: DealGrant, link_id: int, context: AuditContext) -> None:
        link = await db.get(DealLink, link_id)
        if link is None or link.mandate_id != grant.mandate.id:
            raise DealLinkNotFoundError("Link not found")
        await db.delete(link)
        self.audit.record(
            db,
            context,
            "deal_link.removed",
            record_type="mandate",
            record_id=grant.mandate.id,
            old_values={"label": link.label, "url": link.url},
        )
        await db.commit()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_text(item)}" for key, item in value.items() if item is not None)
    return str(value)
