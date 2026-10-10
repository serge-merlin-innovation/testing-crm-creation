"""Which audit rows a reader may see (ROLE-01 c2, AUTHZ-02, AUTHZ-06).

Deal rows carry deal content in their values, so they follow the deal wall: a reader sees the rows of
deals and opportunities they may read, fee rows only with fees.read, and compliance sees every row.
"""

from typing import Any

from sqlalchemy import String, and_, cast, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mandate.policy import DealPolicy
from ..origination.models import Opportunity
from ..origination.service import visible as visible_opportunities
from ..role.authorization import has_permission, is_compliance
from ..role.permissions import Permission
from .models import AuditEntry

MANDATE_RECORDS = ("mandate",)
FEE_RECORDS = ("fee_terms",)
OPPORTUNITY_RECORDS = ("opportunity", "opportunity_fee_draft")
DEAL_RECORDS = MANDATE_RECORDS + FEE_RECORDS + OPPORTUNITY_RECORDS


async def readable_rows(db: AsyncSession, user: dict[str, Any], now: Any) -> Any:
    """A condition on AuditEntry, or None when the reader sees every row."""
    if is_compliance(user):
        return None
    mandate_ids = [str(mandate_id) for mandate_id in await DealPolicy(now).visible_mandate_ids(db, user)]
    opportunity_ids = select(cast(Opportunity.id, String)).where(visible_opportunities(user))
    allowed = [
        not_(AuditEntry.record_type.in_(DEAL_RECORDS)) | AuditEntry.record_type.is_(None),
        and_(AuditEntry.record_type.in_(MANDATE_RECORDS), AuditEntry.record_id.in_(mandate_ids)),
        and_(AuditEntry.record_type.in_(OPPORTUNITY_RECORDS), AuditEntry.record_id.in_(opportunity_ids)),
    ]
    if has_permission(user, Permission.FEES_READ):
        allowed.append(and_(AuditEntry.record_type.in_(FEE_RECORDS), AuditEntry.record_id.in_(mandate_ids)))
    return or_(*allowed)
