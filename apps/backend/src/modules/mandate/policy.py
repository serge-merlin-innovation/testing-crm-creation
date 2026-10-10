"""The single deal-access policy (AUTHZ-02, AUTHZ-03).

Access = role permission AND deal-team membership. Every deal-scoped read and write resolves the
deal through `DealPolicy`, which raises 404 when the caller may not see the deal (never 403, so a
URL does not confirm a deal exists) and 403 when they see it but the action is not theirs.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends
from fastapi.routing import APIRoute
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.clock import Clock, get_clock
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..common.exceptions import DealForbiddenError, DealNotFoundError
from ..role.authorization import has_permission
from ..role.permissions import Permission
from .models import DealTeamMember, Mandate


class DealAction(StrEnum):
    READ = "read"
    EDIT = "edit"
    MANAGE_TEAM = "manage_team"


ACTION_PERMISSION = {
    DealAction.READ: Permission.DEALS_READ_STAFFED,
    DealAction.EDIT: Permission.DEALS_EDIT_STAFFED,
}

# Deal-team roles that may staff the deal, on top of the deal_team.assign permission.
TEAM_MANAGER_ROLES = frozenset({"lead_partner", "partner", "director"})


@dataclass(frozen=True)
class DealGrant:
    mandate: Mandate
    membership: DealTeamMember
    user: dict[str, Any]

    @property
    def can_manage_team(self) -> bool:
        return self.membership.role in TEAM_MANAGER_ROLES or has_permission(self.user, Permission.DEAL_TEAM_ASSIGN)


class DealPolicy:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def _active(self) -> Any:
        return or_(DealTeamMember.expires_at.is_(None), DealTeamMember.expires_at > self.now)

    def visible(self, user: dict[str, Any], query: Select[Any]) -> Select[Any]:
        """Narrows any query over Mandate to the deals this user may read."""
        if not has_permission(user, Permission.DEALS_READ_STAFFED):
            return query.where(Mandate.id.is_(None))
        staffed = select(DealTeamMember.mandate_id).where(DealTeamMember.user_id == user["id"], self._active())
        return query.where(Mandate.id.in_(staffed))

    async def visible_mandate_ids(self, db: AsyncSession, user: dict[str, Any]) -> list[int]:
        return list((await db.execute(self.visible(user, select(Mandate.id)))).scalars())

    async def authorize(self, db: AsyncSession, user: dict[str, Any], mandate_id: int, action: DealAction) -> DealGrant:
        row = (
            await db.execute(
                select(Mandate, DealTeamMember)
                .join(DealTeamMember, DealTeamMember.mandate_id == Mandate.id)
                .where(Mandate.id == mandate_id, DealTeamMember.user_id == user["id"], self._active())
            )
        ).first()
        if row is None or not has_permission(user, Permission.DEALS_READ_STAFFED):
            raise DealNotFoundError(f"Deal {mandate_id} not visible")
        grant = DealGrant(mandate=row[0], membership=row[1], user=user)
        if action == DealAction.MANAGE_TEAM:
            if not grant.can_manage_team:
                raise DealForbiddenError("Only the deal partner or director manages the team")
        elif action in ACTION_PERMISSION and not has_permission(user, ACTION_PERMISSION[action]):
            raise DealForbiddenError(f"Missing {ACTION_PERMISSION[action].value}")
        return grant


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
