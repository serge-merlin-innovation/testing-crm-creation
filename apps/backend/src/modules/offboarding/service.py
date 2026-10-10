from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.clocked_sessions import ClockedSessionManager
from ..api_access.models import ApiClient, ApiToken
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import UserNotFoundError, ValidationError
from ..contact.models import Contact
from ..mandate.models import DealTeamMember, Mandate, WallCrossing
from ..mandate.schemas import TeamRole
from ..role.permissions import RoleName
from ..task.models import Task
from ..user.models import User
from ..user.service import UserService
from .models import Offboarding
from .schemas import OffboardingConfirmation, OffboardingPreview, OwnedRecord, Reactivated


class OffboardingService:
    def __init__(self, sessions: ClockedSessionManager, audit: AuditService | None = None) -> None:
        self.sessions = sessions
        self.audit = audit or AuditService()
        self.users = UserService(self.audit)

    async def _user(self, db: AsyncSession, user_id: int) -> User:
        user = await db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        return user

    async def _owned(self, db: AsyncSession, user_id: int) -> tuple[list[Contact], list[Task], list[Mandate]]:
        contacts = list((await db.execute(select(Contact).where(Contact.owner_id == user_id).order_by(Contact.id))).scalars())
        tasks = list(
            (
                await db.execute(select(Task).where(Task.assignee_id == user_id, Task.completed_at.is_(None)).order_by(Task.id))
            ).scalars()
        )
        deals = list(
            (await db.execute(select(Mandate).where(Mandate.lead_partner_id == user_id).order_by(Mandate.id))).scalars()
        )
        return contacts, tasks, deals

    @staticmethod
    def _records(contacts: list[Contact], tasks: list[Task], deals: list[Mandate]) -> list[OwnedRecord]:
        return [
            *(OwnedRecord(type="contact", id=c.id, label=f"{c.first_name} {c.last_name}") for c in contacts),
            *(OwnedRecord(type="task", id=t.id, label=t.title) for t in tasks),
            # Code name only: the admin is usually not on the deal team.
            *(OwnedRecord(type="deal", id=m.id, label=m.code_name) for m in deals),
        ]

    async def preview(self, db: AsyncSession, user_id: int) -> OffboardingPreview:
        user = await self._user(db, user_id)
        contacts, tasks, deals = await self._owned(db, user_id)
        memberships = len(
            (await db.execute(select(DealTeamMember.id).where(DealTeamMember.user_id == user_id))).scalars().all()
        )
        records = self._records(contacts, tasks, deals)
        return OffboardingPreview(
            user_id=user.id,
            name=user.name,
            contacts=[r for r in records if r.type == "contact"],
            tasks=[r for r in records if r.type == "task"],
            deals=[r for r in records if r.type == "deal"],
            deal_memberships=memberships,
            needs_new_owner=bool(records),
            new_owner_must_be_partner=bool(deals),
        )

    async def _new_owner(self, db: AsyncSession, leaver: User, new_owner_id: int | None, deals: list[Mandate]) -> User:
        if new_owner_id is None:
            raise ValidationError("Choose a new owner for this person's contacts, tasks and deals.", field="new_owner_id")
        owner = await db.get(User, new_owner_id)
        if owner is None or owner.is_deleted or owner.id == leaver.id or owner.role_id is None:
            raise ValidationError("The new owner must be another active user.", field="new_owner_id")
        if deals and owner.role_name != RoleName.PARTNER.value:
            raise ValidationError("This person leads deals: the new owner must be a Partner.", field="new_owner_id")
        return owner

    async def _hand_over_deal(self, db: AsyncSession, deal: Mandate, owner: User, by: int | None, now: datetime) -> None:
        deal.lead_partner_id = owner.id
        deal.version += 1
        member = (
            await db.execute(
                select(DealTeamMember).where(DealTeamMember.mandate_id == deal.id, DealTeamMember.user_id == owner.id)
            )
        ).scalar_one_or_none()
        if member is None:
            db.add(
                DealTeamMember(
                    mandate_id=deal.id,
                    user_id=owner.id,
                    role=TeamRole.LEAD_PARTNER.value,
                    added_by=by or owner.id,
                    added_at=now,
                    expires_at=None,
                )
            )
        else:
            member.role = TeamRole.LEAD_PARTNER.value
            member.expires_at = None
        db.add(
            WallCrossing(
                mandate_id=deal.id,
                user_id=owner.id,
                by_user_id=by or owner.id,
                action="added",
                role=TeamRole.LEAD_PARTNER.value,
                at=now,
            )
        )

    async def deactivate(
        self, db: AsyncSession, user_id: int, new_owner_id: int | None, context: AuditContext
    ) -> OffboardingConfirmation:
        leaver = await self._user(db, user_id)
        if leaver.is_deleted:
            raise ValidationError("This user is already deactivated.", field="user_id")
        await self.users.verify_admin_removal_allowed({"role_name": leaver.role_name}, db)
        now = context.clock.now()
        contacts, tasks, deals = await self._owned(db, user_id)
        reassigned = self._records(contacts, tasks, deals)
        owner = await self._new_owner(db, leaver, new_owner_id, deals) if reassigned else None

        if owner is not None:
            for contact in contacts:
                contact.owner_id = owner.id
            for task in tasks:
                task.assignee_id = owner.id
            for deal in deals:
                await self._hand_over_deal(db, deal, owner, context.user_id, now)

        memberships = list((await db.execute(select(DealTeamMember).where(DealTeamMember.user_id == user_id))).scalars())
        for member in memberships:
            db.add(
                WallCrossing(
                    mandate_id=member.mandate_id,
                    user_id=user_id,
                    by_user_id=context.user_id or user_id,
                    action="removed",
                    role=member.role,
                    at=now,
                )
            )
        await db.execute(delete(DealTeamMember).where(DealTeamMember.user_id == user_id))

        tokens = list(
            (await db.execute(select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None)))).scalars()
        )
        clients = list(
            (await db.execute(select(ApiClient).where(ApiClient.user_id == user_id, ApiClient.revoked_at.is_(None)))).scalars()
        )
        for token in tokens:
            token.revoked_at = now
        for client in clients:
            client.revoked_at = now

        leaver.is_deleted = True
        leaver.deleted_at = now
        sessions_ended = await self.sessions.revoke_all(user_id)

        confirmation = OffboardingConfirmation(
            user_id=user_id,
            at=now,
            sessions_ended=sessions_ended,
            api_tokens_revoked=len(tokens),
            api_clients_revoked=len(clients),
            deal_memberships_removed=len(memberships),
            new_owner_id=owner.id if owner else None,
            new_owner_name=owner.name if owner else None,
            reassigned=reassigned,
        )
        db.add(
            Offboarding(
                user_id=user_id,
                by_user_id=context.user_id,
                new_owner_id=owner.id if owner else None,
                at=now,
                summary=confirmation.model_dump(mode="json"),
            )
        )
        self.audit.record(
            db,
            context,
            "user.deleted",
            record_type="user",
            record_id=user_id,
            old_values={"is_deleted": False},
            new_values={
                "is_deleted": True,
                "sessions_ended": sessions_ended,
                "api_tokens_revoked": len(tokens) + len(clients),
                "new_owner_id": confirmation.new_owner_id,
                "reassigned": len(reassigned),
            },
        )
        await db.commit()
        return confirmation

    async def last_confirmation(self, db: AsyncSession, user_id: int) -> OffboardingConfirmation | None:
        row = (
            await db.execute(select(Offboarding).where(Offboarding.user_id == user_id).order_by(Offboarding.id.desc()).limit(1))
        ).scalar_one_or_none()
        return OffboardingConfirmation.model_validate(row.summary) if row else None

    async def reactivate(self, db: AsyncSession, user_id: int, context: AuditContext) -> Reactivated:
        user = await self._user(db, user_id)
        if not user.is_deleted:
            raise ValidationError("This user is already active.", field="user_id")
        if user.role_id is None:
            raise ValidationError("This account was anonymised and cannot be reactivated.", field="user_id")
        role_name = user.role_name
        user.is_deleted = False
        user.deleted_at = None
        self.audit.record(
            db,
            context,
            "user.reactivated",
            record_type="user",
            record_id=user_id,
            old_values={"is_deleted": True},
            new_values={"is_deleted": False, "role": role_name},
        )
        await db.commit()
        memberships = len(
            (await db.execute(select(DealTeamMember.id).where(DealTeamMember.user_id == user_id))).scalars().all()
        )
        return Reactivated(user_id=user_id, role_name=role_name, deal_memberships=memberships)
