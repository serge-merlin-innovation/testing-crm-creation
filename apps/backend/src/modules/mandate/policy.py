"""The single deal-access policy (AUTHZ-02, AUTHZ-03).

Access = role permission AND deal-team membership. Every deal-scoped read and write resolves the
deal through `DealPolicy`, which raises 404 when the caller may not see the deal (never 403, so a
URL does not confirm a deal exists) and 403 when they see it but the action is not theirs.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends
from fastapi.routing import APIRoute
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.clock import Clock, get_clock
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..common.exceptions import DealClosedError, DealForbiddenError, DealFrozenError, DealNotFoundError
from ..role.authorization import has_permission
from ..role.permissions import Permission
from .models import DealTeamMember, EmergencyAccess, Mandate
from .schemas import ConflictStatus


class DealAction(StrEnum):
    READ = "read"
    EDIT = "edit"
    MANAGE_TEAM = "manage_team"
    REOPEN = "reopen"
    # Compliance work on any deal (conflict decisions, KYC, unfreezing): compliance only.
    COMPLIANCE = "compliance"
    # Reading compliance data: compliance, or anyone who may read the deal.
    COMPLIANCE_READ = "compliance_read"
    # Taking deal data out of the CRM: staffed members only, never break-glass (AUTHZ-08 c3).
    EXPORT = "export"


ACTION_PERMISSION = {
    DealAction.READ: Permission.DEALS_READ_STAFFED,
    DealAction.EDIT: Permission.DEALS_EDIT_STAFFED,
}

# Deal-team roles that may staff the deal, on top of the deal_team.assign permission.
TEAM_MANAGER_ROLES = frozenset({"lead_partner", "partner", "director"})
# Deal-team roles that may close and reopen the deal (DEAL-06).
CLOSER_ROLES = frozenset({"lead_partner", "partner"})
# A deal closed this long ago opens to compliance, read-only (AUTHZ-02 c8).
COMPLIANCE_AFTER_CLOSE = timedelta(days=365)


@dataclass(frozen=True)
class DealGrant:
    mandate: Mandate
    # None for compliance reading a long-closed deal they were never staffed on.
    membership: DealTeamMember | None
    user: dict[str, Any]
    # Admin break-glass (AUTHZ-08): read-only, no exports.
    emergency: bool = False

    @property
    def is_closed(self) -> bool:
        return self.mandate.closed_at is not None

    @property
    def is_frozen(self) -> bool:
        return self.mandate.frozen_at is not None

    @property
    def can_edit(self) -> bool:
        return (
            self.membership is not None
            and not self.is_closed
            and not self.is_frozen
            and has_permission(self.user, Permission.DEALS_EDIT_STAFFED)
        )

    @property
    def can_manage_team(self) -> bool:
        if self.membership is None or self.is_closed or self.is_frozen:
            return False
        return self.membership.role in TEAM_MANAGER_ROLES or has_permission(self.user, Permission.DEAL_TEAM_ASSIGN)

    @property
    def is_closer(self) -> bool:
        return (
            self.membership is not None
            and self.membership.role in CLOSER_ROLES
            and has_permission(self.user, Permission.DEALS_EDIT_STAFFED)
        )


def is_compliance(user: dict[str, Any]) -> bool:
    return has_permission(user, Permission.CONFLICTS_REGISTER)


def in_conflict_hiding() -> Any:
    """Deals only their creator and compliance may find (DEAL-01 c4): awaiting the first conflict
    decision, or rejected. A running deal whose new counterparty is under review stays with its team."""
    return or_(
        and_(Mandate.conflict_status == ConflictStatus.REVIEW.value, Mandate.stage == "conflict_review"),
        Mandate.conflict_status == ConflictStatus.REJECTED.value,
    )


class DealPolicy:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def _active(self) -> Any:
        return or_(DealTeamMember.expires_at.is_(None), DealTeamMember.expires_at > self.now)

    def _compliance_window(self) -> Any:
        return and_(Mandate.closed_at.is_not(None), Mandate.closed_at <= self.now - COMPLIANCE_AFTER_CLOSE)

    def _emergency(self, user: dict[str, Any]) -> Any:
        return select(EmergencyAccess.mandate_id).where(
            EmergencyAccess.user_id == user["id"], EmergencyAccess.expires_at > self.now
        )

    def _not_hidden_from(self, user: dict[str, Any]) -> Any:
        return or_(~in_conflict_hiding(), Mandate.created_by == user["id"])

    def visible(self, user: dict[str, Any], query: Select[Any]) -> Select[Any]:
        """Narrows any query over Mandate to the deals this user may read."""
        conditions = []
        if has_permission(user, Permission.DEALS_READ_STAFFED):
            staffed = select(DealTeamMember.mandate_id).where(DealTeamMember.user_id == user["id"], self._active())
            conditions.append(and_(Mandate.id.in_(staffed), self._not_hidden_from(user)))
        if has_permission(user, Permission.DEALS_READ_SUMMARY):
            conditions.append(self._compliance_window())
        if is_compliance(user):
            conditions.append(in_conflict_hiding())
        conditions.append(Mandate.id.in_(self._emergency(user)))
        if not conditions:
            return query.where(Mandate.id.is_(None))
        return query.where(or_(*conditions))

    async def visible_mandate_ids(self, db: AsyncSession, user: dict[str, Any]) -> list[int]:
        return list((await db.execute(self.visible(user, select(Mandate.id)))).scalars())

    async def authorize(self, db: AsyncSession, user: dict[str, Any], mandate_id: int, action: DealAction) -> DealGrant:
        row = (
            await db.execute(
                select(Mandate, DealTeamMember)
                .join(DealTeamMember, DealTeamMember.mandate_id == Mandate.id)
                .where(
                    Mandate.id == mandate_id,
                    DealTeamMember.user_id == user["id"],
                    self._active(),
                    self._not_hidden_from(user),
                )
            )
        ).first()
        if action in (DealAction.COMPLIANCE, DealAction.COMPLIANCE_READ) and is_compliance(user):
            mandate = await db.get(Mandate, mandate_id)
            if mandate is None:
                raise DealNotFoundError(f"Deal {mandate_id} not found")
            return DealGrant(mandate=mandate, membership=row[1] if row else None, user=user)
        if row is not None and has_permission(user, Permission.DEALS_READ_STAFFED):
            grant = DealGrant(mandate=row[0], membership=row[1], user=user)
        elif (emergency := await self._emergency_grant(db, user, mandate_id)) is not None:
            if action != DealAction.READ:
                raise DealForbiddenError("Break-glass access is read-only")
            return emergency
        else:
            grant = await self._compliance_grant(db, user, mandate_id)
        if action in (DealAction.READ, DealAction.COMPLIANCE_READ):
            return grant
        if action == DealAction.COMPLIANCE:
            raise DealForbiddenError("Only compliance does this")
        if grant.membership is None:
            if action == DealAction.EXPORT:
                raise DealForbiddenError("Only the deal team exports a deal")
            raise DealForbiddenError("Compliance reads a closed deal, never edits it")
        if action == DealAction.EXPORT:
            return grant
        if action == DealAction.REOPEN:
            if not grant.is_closer:
                raise DealForbiddenError("Only a partner on the deal reopens it")
            return grant
        if grant.is_frozen:
            raise DealFrozenError("The deal is frozen")
        if grant.is_closed:
            raise DealClosedError("The deal is closed")
        if action == DealAction.MANAGE_TEAM:
            if not grant.can_manage_team:
                raise DealForbiddenError("Only the deal partner or director manages the team")
        elif action in ACTION_PERMISSION and not has_permission(user, ACTION_PERMISSION[action]):
            raise DealForbiddenError(f"Missing {ACTION_PERMISSION[action].value}")
        return grant

    async def _emergency_grant(self, db: AsyncSession, user: dict[str, Any], mandate_id: int) -> DealGrant | None:
        mandate = (
            await db.execute(select(Mandate).where(Mandate.id == mandate_id, Mandate.id.in_(self._emergency(user))))
        ).scalar_one_or_none()
        return None if mandate is None else DealGrant(mandate=mandate, membership=None, user=user, emergency=True)

    async def authorize_summary(self, db: AsyncSession, user: dict[str, Any], mandate_id: int) -> DealGrant:
        """The read-only deal summary (ROLE-01 c4): the team, or a deals.read_summary holder on any deal.

        Only the summary, fee and invoice routes use this grant: every other deal route keeps `authorize`.
        """
        try:
            return await self.authorize(db, user, mandate_id, DealAction.READ)
        except DealNotFoundError:
            if not has_permission(user, Permission.DEALS_READ_SUMMARY):
                raise
        mandate = await db.get(Mandate, mandate_id)
        if mandate is None:
            raise DealNotFoundError(f"Deal {mandate_id} not found")
        return DealGrant(mandate=mandate, membership=None, user=user)

    async def _compliance_grant(self, db: AsyncSession, user: dict[str, Any], mandate_id: int) -> DealGrant:
        windows = []
        if has_permission(user, Permission.DEALS_READ_SUMMARY):
            windows.append(self._compliance_window())
        if is_compliance(user):
            windows.append(in_conflict_hiding())
        if windows:
            mandate = (await db.execute(select(Mandate).where(Mandate.id == mandate_id, or_(*windows)))).scalar_one_or_none()
            if mandate is not None:
                return DealGrant(mandate=mandate, membership=None, user=user)
        raise DealNotFoundError(f"Deal {mandate_id} not visible")


def deal_access(action: DealAction) -> Any:
    """Route dependency: resolves `{mandate_id}` through the policy for `action`."""

    async def dependency(
        mandate_id: int,
        db: AsyncSessionDep,
        user: CurrentUserDep,
        clock: Annotated[Clock, Depends(get_clock)],
    ) -> DealGrant:
        return await DealPolicy(clock.now()).authorize(db, user, mandate_id, action)

    dependency.__name__ = f"deal_access_{action.value}"
    setattr(dependency, DEAL_SCOPED_MARK, True)
    return Depends(dependency)


DEAL_SCOPED_MARK = "__deal_scoped__"


def mark_deal_scoped(dependency: Callable[..., Any]) -> Callable[..., Any]:
    """Flags a dependency that resolves `{mandate_id}`, so the access-matrix guard sees its routes."""
    setattr(dependency, DEAL_SCOPED_MARK, True)
    return dependency


async def _summary_dependency(
    mandate_id: int,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    clock: Annotated[Clock, Depends(get_clock)],
) -> DealGrant:
    return await DealPolicy(clock.now()).authorize_summary(db, user, mandate_id)


mark_deal_scoped(_summary_dependency)


def _dependencies(call: Callable[..., Any] | None, dependant: Any) -> bool:
    if call is not None and getattr(call, DEAL_SCOPED_MARK, False):
        return True
    return any(_dependencies(sub.call, sub) for sub in dependant.dependencies)


@dataclass(frozen=True)
class ServedRoute:
    method: str
    path: str
    deal_scoped: bool


def served_routes(routes: Iterable[Any]) -> list[ServedRoute]:
    """Every API operation the app serves, flagged when it resolves a deal through this policy.

    The access matrix test reads this, so a deal endpoint cannot ship without a matrix row.
    """
    served: list[ServedRoute] = []
    for route in routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is not None:
            candidates: Iterable[Any] = contexts()
        elif isinstance(route, APIRoute):
            candidates = [route]
        else:
            continue
        for candidate in candidates:
            dependant = getattr(candidate, "dependant", None)
            if dependant is None:
                continue
            scoped = _dependencies(None, dependant)
            for method in sorted((candidate.methods or set()) - {"HEAD", "OPTIONS"}):
                served.append(ServedRoute(method, candidate.path, scoped))
    return served


ReadGrant = Annotated[DealGrant, deal_access(DealAction.READ)]
EditGrant = Annotated[DealGrant, deal_access(DealAction.EDIT)]
TeamGrant = Annotated[DealGrant, deal_access(DealAction.MANAGE_TEAM)]
ReopenGrant = Annotated[DealGrant, deal_access(DealAction.REOPEN)]
SummaryGrant = Annotated[DealGrant, Depends(_summary_dependency)]
ComplianceGrant = Annotated[DealGrant, deal_access(DealAction.COMPLIANCE)]
ExportGrant = Annotated[DealGrant, deal_access(DealAction.EXPORT)]
ComplianceReadGrant = Annotated[DealGrant, deal_access(DealAction.COMPLIANCE_READ)]
