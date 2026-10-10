import csv
import io
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService, audit_export
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError
from ..common.spreadsheet import safe_row
from ..contact.models import Contact
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..role.authorization import has_permission
from ..role.permissions import Permission, RoleName
from ..user.models import User
from ..user.service import display_name
from .models import ExportApproval
from .schemas import ApprovalStatus, ContactFilter

APPROVAL_LIMIT = 500
CONTACTS = "contacts"
# REP-06 names the Analyst role; other roles export without a second pair of eyes, but always logged.
LIMITED_ROLES = frozenset({RoleName.ANALYST.value})
COLUMNS = ["id", "first_name", "last_name", "email", "phone", "language", "legal_basis", "do_not_contact"]


class ApprovalRequiredError(Exception):
    pass


def _matching(values: ContactFilter) -> Any:
    query = select(Contact)
    if values.q and values.q.strip():
        term = values.q.strip()
        query = query.where(
            or_(
                Contact.first_name.icontains(term, autoescape=True),
                Contact.last_name.icontains(term, autoescape=True),
                Contact.email.icontains(term, autoescape=True),
            )
        )
    return query


class DataExportService:
    def __init__(self, notifications: NotificationService, audit: AuditService | None = None) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()

    async def count(self, db: AsyncSession, values: ContactFilter) -> int:
        return (await db.execute(select(func.count()).select_from(_matching(values).subquery()))).scalar_one()

    @staticmethod
    def needs_approval(user: dict[str, Any], rows: int) -> bool:
        return user.get("role_name") in LIMITED_ROLES and rows > APPROVAL_LIMIT

    async def _approval(self, db: AsyncSession, user: dict[str, Any], values: ContactFilter) -> ExportApproval | None:
        query = select(ExportApproval).where(
            ExportApproval.requested_by == user["id"],
            ExportApproval.kind == CONTACTS,
            ExportApproval.status == ApprovalStatus.APPROVED.value,
            ExportApproval.used_at.is_(None),
        )
        wanted = values.model_dump()
        return next((a for a in (await db.execute(query)).scalars() if a.filter == wanted), None)

    async def export_contacts(
        self, db: AsyncSession, user: dict[str, Any], values: ContactFilter, context: AuditContext
    ) -> str:
        rows = await self.count(db, values)
        approval = None
        if self.needs_approval(user, rows):
            approval = await self._approval(db, user, values)
            if approval is None:
                raise ApprovalRequiredError(rows)
            approval.used_at = context.clock.now()
        contacts = (await db.execute(_matching(values).order_by(Contact.last_name, Contact.first_name, Contact.id))).scalars()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(safe_row(COLUMNS))
        written = 0
        for contact in contacts:
            writer.writerow(safe_row([getattr(contact, column) for column in COLUMNS]))
            written += 1
        audit_export(
            db,
            context,
            CONTACTS,
            record_type=CONTACTS,
            filters=values.model_dump(),
            rows=written,
            approval_id=approval.id if approval else None,
        )
        await db.commit()
        return buffer.getvalue()

    async def request_approval(
        self, db: AsyncSession, user: dict[str, Any], values: ContactFilter, reason: str, context: AuditContext
    ) -> dict[str, Any]:
        now = context.clock.now()
        approval = ExportApproval(
            requested_by=user["id"],
            kind=CONTACTS,
            filter=values.model_dump(),
            row_count=await self.count(db, values),
            reason=reason.strip(),
            requested_at=now,
        )
        db.add(approval)
        await db.flush()
        partners = (await db.execute(select(User).where(User.is_deleted.is_(False)))).scalars()
        for partner in partners:
            if has_permission({"permissions": partner.permissions}, Permission.EXPORTS_APPROVE):
                await self.notifications.add(
                    db,
                    Message(
                        user_id=partner.id,
                        email=partner.email,
                        kind=EventKind.EXPORT_APPROVAL.value,
                        title="An export needs your approval",
                        body=f"{user['name']} asks to export {approval.row_count} contacts: {approval.reason}",
                        link="/exports",
                    ),
                    now,
                )
        self.audit.record(
            db,
            context,
            "export.approval_requested",
            record_type="export_approval",
            record_id=approval.id,
            new_values={"filter": approval.filter, "rows": approval.row_count},
        )
        await db.commit()
        await self.notifications.flush_emails()
        return await self.read(db, approval)

    async def read(self, db: AsyncSession, approval: ExportApproval) -> dict[str, Any]:
        requester = await db.get(User, approval.requested_by)
        return {
            "id": approval.id,
            "requested_by": approval.requested_by,
            "requested_by_name": display_name(requester.name, requester.is_deleted) if requester else None,
            "kind": approval.kind,
            "filter": approval.filter,
            "row_count": approval.row_count,
            "reason": approval.reason,
            "requested_at": approval.requested_at,
            "status": approval.status,
            "decided_by": approval.decided_by,
            "decided_at": approval.decided_at,
            "used_at": approval.used_at,
        }

    async def list(self, db: AsyncSession, user: dict[str, Any]) -> list[dict[str, Any]]:
        query = select(ExportApproval).order_by(ExportApproval.requested_at.desc(), ExportApproval.id.desc())
        if not has_permission(user, Permission.EXPORTS_APPROVE):
            query = query.where(ExportApproval.requested_by == user["id"])
        return [await self.read(db, a) for a in (await db.execute(query)).scalars()]

    async def decide(
        self, db: AsyncSession, user: dict[str, Any], approval_id: int, approve: bool, context: AuditContext
    ) -> dict[str, Any]:
        approval = await db.get(ExportApproval, approval_id)
        if approval is None:
            raise ResourceNotFoundError("Export request not found")
        if approval.requested_by == user["id"]:
            raise PermissionDeniedError("Nobody approves their own export")
        if approval.status != ApprovalStatus.PENDING.value:
            return await self.read(db, approval)
        approval.status = (ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED).value
        approval.decided_by = user["id"]
        approval.decided_at = context.clock.now()
        self.audit.record(
            db,
            context,
            "export.approval_decided",
            record_type="export_approval",
            record_id=approval.id,
            new_values={"status": approval.status},
        )
        await db.commit()
        return await self.read(db, approval)
