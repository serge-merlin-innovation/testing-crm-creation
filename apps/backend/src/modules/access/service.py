"""Wall-crossing requests (AUTHZ-04), delegation (AUTHZ-07), break-glass (AUTHZ-08) and the quarterly
access review (ADM-05).

Approvers and delegates are not on the deal team, so nothing here reads the deal through
`DealPolicy`: they get the request context only, and the deal stays hidden from them.
"""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import (
    AccessRequestNotFoundError,
    AccessReviewNotFoundError,
    DealNotFoundError,
    PermissionDeniedError,
    ResourceExistsError,
    ValidationError,
)
from ..company.models import Company
from ..compliance.models import DealCounterparty
from ..compliance.service import ConflictService
from ..mandate.models import DealTeamMember, EmergencyAccess, Mandate
from ..mandate.policy import in_conflict_hiding
from ..mandate.schemas import TeamRole
from ..mandate.service import MandateService
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..role.authorization import has_permission
from ..role.permissions import Permission
from ..task.models import Task
from ..user.models import User
from .models import AccessRequest, AccessRequestApprover, AccessRequestComment, AccessReview, Delegation
from .schemas import (
    AccessDecision,
    AccessRequestCreate,
    AccessReviewSubmit,
    BreakGlassCreate,
    CommentCreate,
    Decision,
    DelegationCreate,
    RequestStatus,
)

DEFAULT_ACCESS = timedelta(days=30)
BREAK_GLASS_FOR = timedelta(hours=4)
REVIEW_WINDOW = timedelta(days=14)
# Who the requester joins the team as: no team-management rights, no closing rights.
CROSSING_ROLE = TeamRole.OTHER


def quarter_of(moment: datetime) -> str:
    return f"{moment.year}-Q{(moment.month - 1) // 3 + 1}"


def quarter_start(moment: datetime) -> datetime:
    return moment.replace(month=(moment.month - 1) // 3 * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def is_compliance(user: dict[str, Any]) -> bool:
    return has_permission(user, Permission.CONFLICTS_REGISTER)


def _required(text: str | None, field: str) -> str:
    if text is None or not text.strip():
        raise ValidationError("A reason is required", field=field)
    return text.strip()


async def _users_with(db: AsyncSession, permission: Permission) -> list[User]:
    users = (await db.execute(select(User).where(User.is_deleted.is_(False), User.role_id.is_not(None)))).scalars()
    return [user for user in users if permission.value in (user.permissions or [])]


async def _names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(list((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples()))


def comment_label(author: str, on_behalf_of: str | None, recommendation: str | None) -> str:
    verb = {"approve": "Approved", "reject": "Rejected"}.get(recommendation or "", "Comment")
    text = f"{verb} by {author}"
    return f"{text} on behalf of {on_behalf_of}" if on_behalf_of else text


class AccessService:
    def __init__(self, notifications: NotificationService, audit: AuditService | None = None) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()
        self.mandates = MandateService(notifications, self.audit)

    # Lookups

    async def _open_deal(self, db: AsyncSession, code_name: str) -> Mandate:
        """An open deal by exact code name. Closed and conflict-hidden deals read as missing."""
        mandate = (
            await db.execute(
                select(Mandate).where(
                    Mandate.code_name_key == code_name.strip().lower(), Mandate.closed_at.is_(None), ~in_conflict_hiding()
                )
            )
        ).scalar_one_or_none()
        if mandate is None:
            raise DealNotFoundError("No open deal has this code name")
        return mandate

    async def _deal_partners(self, db: AsyncSession, mandate_id: int, now: datetime) -> list[int]:
        rows = await db.execute(
            select(DealTeamMember.user_id).where(
                DealTeamMember.mandate_id == mandate_id,
                DealTeamMember.role == TeamRole.LEAD_PARTNER.value,
                or_(DealTeamMember.expires_at.is_(None), DealTeamMember.expires_at > now),
            )
        )
        return list(rows.scalars())

    async def _active_delegations(self, db: AsyncSession, partner_ids: list[int], today: date) -> list[Delegation]:
        query = select(Delegation).where(
            Delegation.partner_id.in_(partner_ids), Delegation.starts_on <= today, Delegation.ends_on >= today
        )
        return list((await db.execute(query)).scalars())

    def _active_delegation_ids(self, today: date) -> Any:
        return select(Delegation.id).where(Delegation.starts_on <= today, Delegation.ends_on >= today)

    async def _approver(self, db: AsyncSession, request_id: int, user_id: int, today: date) -> AccessRequestApprover | None:
        """The user's approver row, if they still hold it: a delegate's ends with the delegation."""
        return (
            await db.execute(
                select(AccessRequestApprover).where(
                    AccessRequestApprover.request_id == request_id,
                    AccessRequestApprover.user_id == user_id,
                    or_(
                        AccessRequestApprover.delegation_id.is_(None),
                        AccessRequestApprover.delegation_id.in_(self._active_delegation_ids(today)),
                    ),
                )
            )
        ).scalar_one_or_none()

    async def _visible_request(
        self, db: AsyncSession, user: dict[str, Any], request_id: int, now: datetime
    ) -> tuple[AccessRequest, AccessRequestApprover | None]:
        request = await db.get(AccessRequest, request_id)
        if request is None:
            raise AccessRequestNotFoundError("Access request not found")
        approver = await self._approver(db, request_id, user["id"], now.date())
        if approver is None and not is_compliance(user):
            raise AccessRequestNotFoundError("Access request not found")
        return request, approver

    # Requests

    async def request(self, db: AsyncSession, values: AccessRequestCreate, context: AuditContext) -> dict[str, Any]:
        assert context.user_id is not None
        reason = _required(values.reason, "reason")
        mandate = await self._open_deal(db, values.code_name)
        now = context.clock.now()
        if context.user_id in await self._staffed_ids(db, mandate.id, now):
            raise ResourceExistsError("You are already on this deal")
        pending = await db.execute(
            select(AccessRequest.id).where(
                AccessRequest.mandate_id == mandate.id,
                AccessRequest.requester_id == context.user_id,
                AccessRequest.status == RequestStatus.PENDING.value,
            )
        )
        if pending.first() is not None:
            raise ResourceExistsError("You already asked for this deal")

        request = AccessRequest(
            mandate_id=mandate.id,
            requester_id=context.user_id,
            reason=reason,
            status=RequestStatus.PENDING.value,
            created_at=now,
        )
        db.add(request)
        await db.flush()

        partners = await self._deal_partners(db, mandate.id, now)
        approvers: dict[int, tuple[int | None, int | None]] = {pid: (None, None) for pid in partners}
        for delegation in await self._active_delegations(db, partners, now.date()):
            approvers.setdefault(delegation.delegate_id, (delegation.partner_id, delegation.id))
        for compliance in await _users_with(db, Permission.CONFLICTS_REGISTER):
            approvers.setdefault(compliance.id, (None, None))
        approvers.pop(context.user_id, None)

        title = f"Approve wall-crossing request on {mandate.code_name}"
        for user_id, (on_behalf_of, delegation_id) in approvers.items():
            user = await db.get(User, user_id)
            assert user is not None
            # The deal partner is on the team; compliance and delegates are not, so the task links no deal.
            task = Task(
                title=title,
                assignee_id=user_id,
                created_by=context.user_id,
                due_date=now.date(),
                recurrence="none",
                created_at=now,
            )
            db.add(task)
            await db.flush()
            db.add(
                AccessRequestApprover(
                    request_id=request.id,
                    user_id=user_id,
                    task_id=task.id,
                    on_behalf_of_id=on_behalf_of,
                    delegation_id=delegation_id,
                )
            )
            await self.notifications.add(
                db,
                Message(
                    user_id=user_id,
                    email=user.email,
                    kind=EventKind.ACCESS_REQUESTED.value,
                    title=f"Wall-crossing request on {mandate.code_name}",
                    body=f"Someone asked to join {mandate.code_name}. Open the request to review it.",
                    link=f"/access?request={request.id}",
                ),
                now,
            )
        self.audit.record(
            db,
            context,
            "access.requested",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"request_id": request.id, "requester_id": context.user_id},
        )
        await db.commit()
        await self.notifications.flush_emails()
        return await self._mine_item(db, request, mandate)

    async def _staffed_ids(self, db: AsyncSession, mandate_id: int, now: datetime) -> set[int]:
        rows = await db.execute(
            select(DealTeamMember.user_id).where(
                DealTeamMember.mandate_id == mandate_id,
                or_(DealTeamMember.expires_at.is_(None), DealTeamMember.expires_at > now),
            )
        )
        return set(rows.scalars())

    async def _mine_item(self, db: AsyncSession, request: AccessRequest, mandate: Mandate) -> dict[str, Any]:
        return {
            "id": request.id,
            "code_name": mandate.code_name,
            "reason": request.reason,
            "status": request.status,
            "created_at": request.created_at,
            "decision_reason": request.decision_reason,
            "expires_at": request.expires_at,
        }

    async def mine(self, db: AsyncSession, user: dict[str, Any]) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(AccessRequest, Mandate)
            .join(Mandate, Mandate.id == AccessRequest.mandate_id)
            .where(AccessRequest.requester_id == user["id"])
            .order_by(AccessRequest.created_at.desc(), AccessRequest.id.desc())
        )
        return [await self._mine_item(db, request, mandate) for request, mandate in rows.tuples()]

    async def queue(self, db: AsyncSession, user: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
        """Pending requests the caller approves (compliance: every one)."""
        query = (
            select(AccessRequest, Mandate.code_name, User.name)
            .join(Mandate, Mandate.id == AccessRequest.mandate_id)
            .join(User, User.id == AccessRequest.requester_id)
            .where(AccessRequest.status == RequestStatus.PENDING.value)
            .order_by(AccessRequest.created_at, AccessRequest.id)
        )
        if not is_compliance(user):
            mine = select(AccessRequestApprover.request_id).where(
                AccessRequestApprover.user_id == user["id"],
                or_(
                    AccessRequestApprover.delegation_id.is_(None),
                    AccessRequestApprover.delegation_id.in_(self._active_delegation_ids(now.date())),
                ),
            )
            query = query.where(AccessRequest.id.in_(mine))
        return [
            {
                "id": request.id,
                "code_name": code_name,
                "requester_name": requester,
                "reason": request.reason,
                "status": request.status,
                "created_at": request.created_at,
            }
            for request, code_name, requester in (await db.execute(query)).tuples()
        ]

    async def context(self, db: AsyncSession, user: dict[str, Any], request_id: int, now: datetime) -> dict[str, Any]:
        request, approver = await self._visible_request(db, user, request_id, now)
        mandate = await db.get(Mandate, request.mandate_id)
        assert mandate is not None
        comments = list(
            (
                await db.execute(
                    select(AccessRequestComment)
                    .where(AccessRequestComment.request_id == request.id)
                    .order_by(AccessRequestComment.created_at, AccessRequestComment.id)
                )
            ).scalars()
        )
        ids = (
            {request.requester_id}
            | {c.author_id for c in comments}
            | {c.on_behalf_of_id for c in comments if c.on_behalf_of_id}
        )
        if request.decided_by:
            ids.add(request.decided_by)
        names = await _names(db, ids)
        pending = request.status == RequestStatus.PENDING.value
        return {
            "id": request.id,
            "code_name": mandate.code_name,
            "requester_id": request.requester_id,
            "requester_name": names[request.requester_id],
            "reason": request.reason,
            "status": request.status,
            "created_at": request.created_at,
            "decision_reason": request.decision_reason,
            "decided_by_name": names.get(request.decided_by) if request.decided_by else None,
            "expires_at": request.expires_at,
            "conflicts": await self.conflicts(db, mandate, request.requester_id, now) if is_compliance(user) else [],
            "comments": [
                {
                    "author_name": names[c.author_id],
                    "on_behalf_of_name": names.get(c.on_behalf_of_id) if c.on_behalf_of_id else None,
                    "body": c.body,
                    "recommendation": c.recommendation,
                    "label": comment_label(
                        names[c.author_id], names.get(c.on_behalf_of_id) if c.on_behalf_of_id else None, c.recommendation
                    ),
                    "created_at": c.created_at,
                }
                for c in comments
            ],
            "can_decide": pending and is_compliance(user),
            "can_comment": pending and (approver is not None or is_compliance(user)),
        }

    async def conflicts(self, db: AsyncSession, mandate: Mandate, requester_id: int, now: datetime) -> list[dict[str, Any]]:
        """The requester's own deals that sit on the other side of the requested one (AUTHZ-04 c5)."""
        staffed = set(
            (
                await db.execute(
                    select(DealTeamMember.mandate_id).where(
                        DealTeamMember.user_id == requester_id,
                        DealTeamMember.mandate_id != mandate.id,
                        or_(DealTeamMember.expires_at.is_(None), DealTeamMember.expires_at > now),
                    )
                )
            ).scalars()
        )
        if not staffed:
            return []
        parties = [(mandate.client_id, "client")]
        if mandate.target_id is not None:
            parties.append((mandate.target_id, "target"))
        counterparties = await db.execute(select(DealCounterparty.company_id).where(DealCounterparty.mandate_id == mandate.id))
        parties += [(company_id, "counterparty") for company_id in counterparties.scalars()]
        found: dict[int, dict[str, Any]] = {}
        for hit in await ConflictService(self.notifications).find_hits(db, mandate, parties, now):
            if hit.other_mandate_id not in staffed or hit.other_mandate_id in found:
                continue
            other = await db.get(Mandate, hit.other_mandate_id)
            company = await db.get(Company, hit.matched_company_id)
            assert other is not None
            assert company is not None
            found[other.id] = {"mandate_id": other.id, "code_name": other.code_name, "company_name": company.name}
        return sorted(found.values(), key=lambda item: item["code_name"])

    async def comment(
        self, db: AsyncSession, user: dict[str, Any], request_id: int, values: CommentCreate, context: AuditContext
    ) -> dict[str, Any]:
        now = context.clock.now()
        request, approver = await self._visible_request(db, user, request_id, now)
        if request.status != RequestStatus.PENDING.value:
            raise ResourceExistsError("This request is already decided")
        db.add(
            AccessRequestComment(
                request_id=request.id,
                author_id=user["id"],
                body=values.body.strip(),
                created_at=now,
                recommendation=values.recommendation.value if values.recommendation else None,
                on_behalf_of_id=approver.on_behalf_of_id if approver else None,
            )
        )
        self.audit.record(
            db,
            context,
            "access_request.commented",
            record_type="access_request",
            record_id=request.id,
            new_values={"recommendation": values.recommendation.value if values.recommendation else None},
        )
        await db.commit()
        return await self.context(db, user, request_id, now)

    async def decide(
        self, db: AsyncSession, user: dict[str, Any], request_id: int, values: AccessDecision, context: AuditContext
    ) -> dict[str, Any]:
        now = context.clock.now()
        request, _ = await self._visible_request(db, user, request_id, now)
        if not is_compliance(user):
            raise PermissionDeniedError("Compliance decides; the deal partner comments")
        if request.status != RequestStatus.PENDING.value:
            raise ResourceExistsError("This request is already decided")
        mandate = await db.get(Mandate, request.mandate_id)
        requester = await db.get(User, request.requester_id)
        assert mandate is not None
        assert requester is not None

        if values.decision == Decision.APPROVE:
            expires_at = values.expires_at or now + DEFAULT_ACCESS
            if expires_at <= now:
                raise ValidationError("The access must end in the future", field="expires_at")
            await self.mandates.staff_until(db, mandate, requester.id, CROSSING_ROLE, expires_at, context)
            request.status = RequestStatus.APPROVED.value
            request.expires_at = expires_at
            request.decision_reason = values.reason.strip() if values.reason and values.reason.strip() else None
            title = f"Access to {mandate.code_name} approved"
            body = f"You can work on {mandate.code_name} until {expires_at.date().isoformat()}."
            message = Message(
                user_id=requester.id,
                email=requester.email,
                kind=EventKind.ACCESS_APPROVED.value,
                title=title,
                body=body,
                link=f"/deals/{mandate.id}",
                mandate_id=mandate.id,
            )
        else:
            reason = _required(values.reason, "reason")
            request.status = RequestStatus.REJECTED.value
            request.decision_reason = reason
            # No deal link or id: the deal stays invisible to the requester.
            message = Message(
                user_id=requester.id,
                email=requester.email,
                kind=EventKind.ACCESS_REJECTED.value,
                title=f"Access to {mandate.code_name} rejected",
                body=f"Your request to join {mandate.code_name} was rejected: {reason}",
                link="/access",
            )
        request.decided_by = user["id"]
        request.decided_at = now
        await self._close_tasks(db, request.id, now)
        await self.notifications.add(db, message, now)
        self.audit.record(
            db,
            context,
            f"access.{request.status}",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"request_id": request.id, "requester_id": requester.id, "reason": request.decision_reason},
        )
        await db.commit()
        await self.notifications.flush_emails()
        return await self.context(db, user, request_id, now)

    async def _close_tasks(self, db: AsyncSession, request_id: int, now: datetime) -> None:
        task_ids = select(AccessRequestApprover.task_id).where(AccessRequestApprover.request_id == request_id)
        for task in (await db.execute(select(Task).where(Task.id.in_(task_ids), Task.completed_at.is_(None)))).scalars():
            task.completed_at = now

    # Delegation

    async def delegate(
        self, db: AsyncSession, user: dict[str, Any], values: DelegationCreate, context: AuditContext
    ) -> dict[str, Any]:
        if values.ends_on < values.starts_on:
            raise ValidationError("The range ends before it starts", field="ends_on")
        if values.delegate_id == user["id"]:
            raise ValidationError("Choose someone else", field="delegate_id")
        delegate = await db.get(User, values.delegate_id)
        if delegate is None or delegate.is_deleted or delegate.role_id is None:
            raise ValidationError("This user does not exist or has no role", field="delegate_id")
        delegation = Delegation(
            partner_id=user["id"],
            delegate_id=delegate.id,
            starts_on=values.starts_on,
            ends_on=values.ends_on,
            created_at=context.clock.now(),
        )
        db.add(delegation)
        await db.flush()
        self.audit.record(
            db,
            context,
            "delegation.created",
            record_type="user",
            record_id=user["id"],
            new_values={
                "delegate_id": delegate.id,
                "starts_on": values.starts_on.isoformat(),
                "ends_on": values.ends_on.isoformat(),
            },
        )
        await db.commit()
        return self._delegation(delegation, delegate.name, context.clock.now().date())

    def _delegation(self, delegation: Delegation, name: str, today: date) -> dict[str, Any]:
        return {
            "id": delegation.id,
            "delegate_id": delegation.delegate_id,
            "delegate_name": name,
            "starts_on": delegation.starts_on,
            "ends_on": delegation.ends_on,
            "active": delegation.starts_on <= today <= delegation.ends_on,
        }

    async def delegations(self, db: AsyncSession, user: dict[str, Any], today: date) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(Delegation, User.name)
            .join(User, User.id == Delegation.delegate_id)
            .where(Delegation.partner_id == user["id"], Delegation.ends_on >= today)
            .order_by(Delegation.starts_on, Delegation.id)
        )
        return [self._delegation(delegation, name, today) for delegation, name in rows.tuples()]

    async def end_delegation(self, db: AsyncSession, user: dict[str, Any], delegation_id: int, context: AuditContext) -> None:
        delegation = await db.get(Delegation, delegation_id)
        if delegation is None or delegation.partner_id != user["id"]:
            raise AccessRequestNotFoundError("Delegation not found")
        await db.delete(delegation)
        self.audit.record(
            db,
            context,
            "delegation.removed",
            record_type="user",
            record_id=user["id"],
            old_values={"delegate_id": delegation.delegate_id},
        )
        await db.commit()

    # Break-glass

    async def break_glass(
        self, db: AsyncSession, user: dict[str, Any], values: BreakGlassCreate, context: AuditContext
    ) -> dict[str, Any]:
        if not has_permission(user, Permission.USERS_MANAGE):
            raise PermissionDeniedError("Only an admin breaks the glass")
        reason = _required(values.reason, "reason")
        mandate = (
            await db.execute(select(Mandate).where(Mandate.code_name_key == values.code_name.strip().lower()))
        ).scalar_one_or_none()
        if mandate is None:
            raise DealNotFoundError("No deal has this code name")
        now = context.clock.now()
        access = EmergencyAccess(
            mandate_id=mandate.id, user_id=user["id"], reason=reason, granted_at=now, expires_at=now + BREAK_GLASS_FOR
        )
        db.add(access)
        self.audit.record(
            db,
            context,
            "break_glass",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"reason": reason, "expires_at": access.expires_at.isoformat()},
        )
        watchers = {u.id: u for u in await _users_with(db, Permission.CONFLICTS_REGISTER)}
        for partner_id in await self._deal_partners(db, mandate.id, now):
            partner = await db.get(User, partner_id)
            if partner is not None:
                watchers[partner.id] = partner
        watchers.pop(user["id"], None)
        for watcher in watchers.values():
            await self.notifications.add(
                db,
                Message(
                    user_id=watcher.id,
                    email=watcher.email,
                    kind=EventKind.BREAK_GLASS.value,
                    title=f"Break-glass access to {mandate.code_name}",
                    body=f"{user['name']} opened {mandate.code_name} read-only for 4 hours. Reason: {reason}",
                ),
                now,
            )
        await db.commit()
        await self.notifications.flush_emails()
        return {"mandate_id": mandate.id, "code_name": mandate.code_name, "expires_at": access.expires_at}

    # Quarterly review

    async def open_quarterly_reviews(self, db: AsyncSession, now: datetime) -> None:
        quarter = quarter_of(now)
        reviewed = select(AccessReview.mandate_id).where(AccessReview.quarter == quarter)
        deals = (
            await db.execute(
                select(Mandate).where(
                    Mandate.closed_at.is_(None),
                    Mandate.created_at < quarter_start(now),
                    ~in_conflict_hiding(),
                    Mandate.id.not_in(reviewed),
                )
            )
        ).scalars()
        for mandate in deals:
            partner = await db.get(User, mandate.lead_partner_id)
            if partner is None or partner.is_deleted:
                continue
            due = now + REVIEW_WINDOW
            task = Task(
                title=f"Confirm the {mandate.code_name} team for {quarter}",
                assignee_id=partner.id,
                created_by=partner.id,
                due_date=due.date(),
                recurrence="none",
                created_at=now,
                record_type="mandate",
                record_id=mandate.id,
                mandate_id=mandate.id,
            )
            db.add(task)
            await db.flush()
            db.add(
                AccessReview(
                    mandate_id=mandate.id, partner_id=partner.id, quarter=quarter, opened_at=now, due_at=due, task_id=task.id
                )
            )
            await self.notifications.add(
                db,
                Message(
                    user_id=partner.id,
                    email=partner.email,
                    kind=EventKind.TASK_ASSIGNED.value,
                    title=f"Confirm the {mandate.code_name} team for {quarter}",
                    body=f"Confirm or remove each person staffed on {mandate.code_name} by {due.date().isoformat()}.",
                    link="/access",
                    mandate_id=mandate.id,
                ),
                now,
            )
        await db.commit()
        await self.notifications.flush_emails()

    async def escalate_overdue_reviews(self, db: AsyncSession, now: datetime) -> None:
        rows = (
            await db.execute(
                select(AccessReview, Mandate.code_name, User.name)
                .join(Mandate, Mandate.id == AccessReview.mandate_id)
                .join(User, User.id == AccessReview.partner_id)
                .where(AccessReview.completed_at.is_(None), AccessReview.escalated_at.is_(None), AccessReview.due_at <= now)
            )
        ).tuples()
        compliance = await _users_with(db, Permission.CONFLICTS_REGISTER)
        for review, code_name, partner_name in rows:
            for user in compliance:
                await self.notifications.add(
                    db,
                    Message(
                        user_id=user.id,
                        email=user.email,
                        kind=EventKind.ACCESS_REVIEW_OVERDUE.value,
                        title=f"Access review of {code_name} overdue",
                        body=f"{partner_name} has not confirmed the {code_name} team for {review.quarter} within 14 days.",
                        link="/access",
                    ),
                    now,
                )
            review.escalated_at = now
        await db.commit()
        await self.notifications.flush_emails()

    async def reviews(self, db: AsyncSession, user: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
        query = (
            select(AccessReview, Mandate.code_name, User.name)
            .join(Mandate, Mandate.id == AccessReview.mandate_id)
            .join(User, User.id == AccessReview.partner_id)
            .order_by(AccessReview.due_at.desc(), AccessReview.id)
        )
        if not is_compliance(user):
            query = query.where(AccessReview.partner_id == user["id"])
        items = []
        for review, code_name, partner_name in (await db.execute(query)).tuples():
            members: list[dict[str, Any]] = []
            if review.partner_id == user["id"] and review.completed_at is None:
                members = await self._members(db, review.mandate_id, now)
            items.append(
                {
                    "id": review.id,
                    "mandate_id": review.mandate_id,
                    "code_name": code_name,
                    "quarter": review.quarter,
                    "partner_name": partner_name,
                    "due_at": review.due_at,
                    "completed_at": review.completed_at,
                    "escalated_at": review.escalated_at,
                    "members": members,
                }
            )
        return items

    async def _members(self, db: AsyncSession, mandate_id: int, now: datetime) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(DealTeamMember, User.name)
            .join(User, User.id == DealTeamMember.user_id)
            .where(
                DealTeamMember.mandate_id == mandate_id,
                or_(DealTeamMember.expires_at.is_(None), DealTeamMember.expires_at > now),
            )
            .order_by(User.name)
        )
        return [{"user_id": m.user_id, "name": name, "role": m.role} for m, name in rows.tuples()]

    async def submit_review(
        self, db: AsyncSession, user: dict[str, Any], review_id: int, values: AccessReviewSubmit, context: AuditContext
    ) -> dict[str, Any]:
        now = context.clock.now()
        review = await db.get(AccessReview, review_id)
        if review is None or review.partner_id != user["id"]:
            raise AccessReviewNotFoundError("Access review not found")
        if review.completed_at is not None:
            raise ResourceExistsError("This review is already done")
        mandate = await db.get(Mandate, review.mandate_id)
        assert mandate is not None
        staffed = {m["user_id"] for m in await self._members(db, mandate.id, now)}
        for user_id in dict.fromkeys(values.remove_user_ids):
            if user_id not in staffed:
                raise ValidationError(f"User {user_id} is not on the team", field="remove_user_ids")
            await self.mandates.remove_from(db, mandate, user_id, context)
        review.completed_at = now
        if review.task_id is not None:
            task = await db.get(Task, review.task_id)
            if task is not None and task.completed_at is None:
                task.completed_at = now
        self.audit.record(
            db,
            context,
            "access_review.completed",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"quarter": review.quarter, "removed": list(values.remove_user_ids)},
        )
        await db.commit()
        return next(item for item in await self.reviews(db, user, now) if item["id"] == review.id)
