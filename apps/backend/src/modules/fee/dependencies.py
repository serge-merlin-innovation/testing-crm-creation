from typing import Annotated

from fastapi import Depends

from ..common.exceptions import DealForbiddenError
from ..mandate.policy import DealGrant, SummaryGrant
from ..notification.dependencies import NotificationServiceDep
from ..role.authorization import has_permission
from ..role.permissions import Permission
from .service import FeeService


def get_fee_service(notifications: NotificationServiceDep) -> FeeService:
    return FeeService(notifications)


FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]


def _fee_reader(grant: SummaryGrant) -> DealGrant:
    # A deal the caller may not read is already 404; a readable deal without fees.read is 403.
    if not has_permission(grant.user, Permission.FEES_READ):
        raise DealForbiddenError("Fee fields are hidden from this role")
    return grant


def _invoice_manager(grant: Annotated[DealGrant, Depends(_fee_reader)]) -> DealGrant:
    if not has_permission(grant.user, Permission.INVOICES_MANAGE):
        raise DealForbiddenError("Only back-office records invoices")
    return grant


FeeGrant = Annotated[DealGrant, Depends(_fee_reader)]
InvoiceGrant = Annotated[DealGrant, Depends(_invoice_manager)]
