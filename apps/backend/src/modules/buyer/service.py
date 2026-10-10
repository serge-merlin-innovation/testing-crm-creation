"""The buyer process: investor profiles (CO-04), the long list (BUY-01/02), the status grid (BUY-03) and NDAs (BUY-04)."""

import io
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from openpyxl import Workbook  # type: ignore[import-untyped]
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..activity.models import Activity, ActivityLink
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import CompanyNotFoundError, DealForbiddenError, ValidationError
from ..common.spreadsheet import safe_row
from ..company.models import Company
from ..compliance.service import ConflictService
from ..contact.models import Contact
from ..mandate.models import DealTeamMember, Mandate
from ..mandate.policy import DealAction, DealGrant, DealPolicy
from ..mandate.stages import DealStage
from ..notification.ports import LoggingEmailSender
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..picklist.models import PicklistValue
from ..role.authorization import has_permission
from ..role.permissions import Permission
from ..user.models import User
from .models import BuyerNda, ClientExclusion, DealBuyer, InvestorCriterion, InvestorProfile
from .schemas import (
    Approval,
    BuyersAdd,
    BuyerStatus,
    BuyerUpdate,
    NdaUpdate,
    Stake,
    StatusChange,
    SuggestStake,
    WarningReason,
)

PROFILE_OUTDATED_AFTER = timedelta(days=365)
BUYER_IDLE_AFTER = timedelta(days=14)
NDA_PENDING_DAYS = 10
# Deal stages in which buyers are being worked, so an idle buyer is worth a reminder (BUY-03 c5).
ACTIVE_PHASES = frozenset(
    {
        DealStage.MARKETING,
        DealStage.INFORMATION_MEMORANDUM,
        DealStage.INDICATIVE_OFFERS,
        DealStage.DUE_DILIGENCE,
        DealStage.BINDING_OFFERS,
        DealStage.SPA_NEGOTIATION,
    }
)
# Statuses reachable only after the NDA is signed (BUY-03 c2).
AFTER_NDA = (
    BuyerStatus.IM_SENT,
    BuyerStatus.INDICATIVE_OFFER,
    BuyerStatus.DATA_ROOM_ACCESS,
    BuyerStatus.BINDING_OFFER,
    BuyerStatus.PREFERRED_BIDDER,
)
# Not yet approached: the client's approval alone moves a buyer between these two.
NOT_APPROACHED = (BuyerStatus.LONG_LIST.value, BuyerStatus.CLIENT_APPROVED.value)
ORDER = list(BuyerStatus)
TYPE_LABELS = {
    "target": "Target",
    "strategic_buyer": "Strategic buyer",
    "financial_investor": "Financial investor / PE",
    "lender": "Lender",
    "advisor": "Advisor",
    "other": "Other",
}


async def _group(db: AsyncSession, company_id: int) -> list[Company]:
    return await ConflictService()._group(db, company_id)


async def _is_ancestor(db: AsyncSession, ancestor_id: int, company_id: int) -> bool:
    current: int | None = company_id
    seen: set[int] = set()
    while current is not None and current not in seen:
        if current == ancestor_id:
            return True
        seen.add(current)
        current = (await db.execute(select(Company.parent_id).where(Company.id == current))).scalar_one_or_none()
    return False


def _blank(text: str | None) -> bool:
    return text is None or not text.strip()


def _profile_filters(ev_ebitda: Decimal | None, stake: SuggestStake | None) -> list[Any]:
    filters: list[Any] = []
    if ev_ebitda is not None:
        filters.append(or_(InvestorProfile.ev_ebitda_min.is_(None), InvestorProfile.ev_ebitda_min <= ev_ebitda))
        filters.append(or_(InvestorProfile.ev_ebitda_max.is_(None), InvestorProfile.ev_ebitda_max >= ev_ebitda))
    if stake is not None:
        filters.append(InvestorProfile.stake.in_([stake.value, Stake.BOTH.value]))
    return filters


class InvestorProfileService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def _company(self, db: AsyncSession, company_id: int) -> Company:
        company = await db.get(Company, company_id)
        if company is None:
            raise CompanyNotFoundError(f"Company {company_id} not found")
        return company

    async def _profile(self, db: AsyncSession, company_id: int) -> InvestorProfile | None:
        return (await db.execute(select(InvestorProfile).where(InvestorProfile.company_id == company_id))).scalar_one_or_none()

    async def _profile_row(self, db: AsyncSession, company_id: int) -> InvestorProfile:
        profile = await self._profile(db, company_id)
        if profile is None:
            profile = InvestorProfile(company_id=company_id)
            db.add(profile)
        return profile

    async def read(self, db: AsyncSession, company_id: int, user: dict[str, Any], now: datetime) -> dict[str, Any]:
        await self._company(db, company_id)
        profile = await self._profile(db, company_id)
        criteria = (
            await db.execute(
                select(InvestorCriterion.kind, InvestorCriterion.value_id)
                .where(InvestorCriterion.company_id == company_id)
                .order_by(InvestorCriterion.value_id)
            )
        ).all()
        portfolio = (
            await db.execute(select(Company.id, Company.name).where(Company.parent_id == company_id).order_by(Company.name))
        ).all()
        visible = DealPolicy(now).visible(user, select(Mandate.id)).scalar_subquery()
        declines = (
            await db.execute(
                select(Mandate.id, Mandate.code_name, DealBuyer.decline_reason, DealBuyer.status_changed_at)
                .join(Mandate, Mandate.id == DealBuyer.mandate_id)
                .where(
                    DealBuyer.company_id == company_id,
                    DealBuyer.status == BuyerStatus.DECLINED.value,
                    Mandate.closed_at.is_not(None),
                    Mandate.id.in_(visible),
                )
                .order_by(DealBuyer.status_changed_at.desc())
            )
        ).all()
        updated_at = profile.criteria_updated_at if profile else None
        return {
            "company_id": company_id,
            "has_profile": updated_at is not None,
            "sector_ids": [value for kind, value in criteria if kind == "sector"],
            "country_ids": [value for kind, value in criteria if kind == "country"],
            "ticket_min": profile.ticket_min if profile else None,
            "ticket_max": profile.ticket_max if profile else None,
            "ev_ebitda_min": profile.ev_ebitda_min if profile else None,
            "ev_ebitda_max": profile.ev_ebitda_max if profile else None,
            "stake": profile.stake if profile else None,
            "updated_at": updated_at,
            "outdated": updated_at is not None and now - updated_at > PROFILE_OUTDATED_AFTER,
            "portfolio": [{"id": pid, "name": name} for pid, name in portfolio],
            "declines": [
                {"mandate_id": mid, "code_name": code, "reason": reason, "declined_at": at}
                for mid, code, reason, at in declines
            ],
            "standstill_end": profile.standstill_end if profile else None,
            "non_solicit_end": profile.non_solicit_end if profile else None,
        }

    async def update(
        self, db: AsyncSession, company_id: int, values: Any, user: dict[str, Any], context: AuditContext
    ) -> dict[str, Any]:
        await self._company(db, company_id)
        now = context.clock.now()
        for kind, ids in (("sector", values.sector_ids), ("country", values.country_ids)):
            for value_id in ids:
                value = await db.get(PicklistValue, value_id)
                if value is None or value.kind != kind:
                    raise ValidationError(f"Unknown {kind} {value_id}", field=f"{kind}_ids")
        profile = await self._profile_row(db, company_id)
        old = await self.read(db, company_id, user, now)
        for field in ("ticket_min", "ticket_max", "ev_ebitda_min", "ev_ebitda_max"):
            setattr(profile, field, getattr(values, field))
        profile.stake = values.stake.value if values.stake else None
        profile.criteria_updated_at = now
        profile.criteria_updated_by = context.user_id
        await db.execute(delete(InvestorCriterion).where(InvestorCriterion.company_id == company_id))
        for kind, ids in (("sector", values.sector_ids), ("country", values.country_ids)):
            for value_id in dict.fromkeys(ids):
                db.add(InvestorCriterion(company_id=company_id, kind=kind, value_id=value_id))
        self.audit.record(
            db,
            context,
            "investor_profile.updated",
            record_type="company",
            record_id=company_id,
            old_values={k: str(v) if isinstance(v, Decimal) else v for k, v in old.items() if k in values.model_fields},
            new_values=values.model_dump(mode="json"),
        )
        await db.commit()
        await db.refresh(profile)
        return await self.read(db, company_id, user, now)

    async def link_portfolio(
        self, db: AsyncSession, fund_id: int, portfolio_id: int, user: dict[str, Any], context: AuditContext
    ) -> dict[str, Any]:
        """A PE fund's portfolio company becomes a subsidiary in the fund's group (CO-03), so it is a group entity."""
        await self._company(db, fund_id)
        portfolio = await self._company(db, portfolio_id)
        if await _is_ancestor(db, portfolio_id, fund_id):
            raise ValidationError("This link would create a loop in the group", field="company_id")
        old_parent = portfolio.parent_id
        if old_parent is not None and old_parent != fund_id:
            current = await self._company(db, old_parent)
            raise ValidationError(
                f"{portfolio.name} already belongs to the group of {current.name}: change its parent on the company first",
                field="company_id",
            )
        portfolio.parent_id = fund_id
        self.audit.record(
            db,
            context,
            "company.updated",
            record_type="company",
            record_id=portfolio_id,
            old_values={"parent_id": old_parent},
            new_values={"parent_id": fund_id},
        )
        await db.commit()
        return await self.read(db, fund_id, user, context.clock.now())

    async def client_grants(self, db: AsyncSession, user: dict[str, Any], client_id: int, now: datetime) -> list[DealGrant]:
        """The caller's grants on deals for this client. None: the list does not exist for them (404),
        since its existence alone shows the company is a client."""
        policy = DealPolicy(now)
        mandate_ids = list(
            (await db.execute(policy.visible(user, select(Mandate.id).where(Mandate.client_id == client_id)))).scalars()
        )
        grants = [await policy.authorize(db, user, mandate_id, DealAction.READ) for mandate_id in mandate_ids]
        if not grants:
            raise CompanyNotFoundError(f"Company {client_id} not found")
        return grants

    async def require_exclusion_manager(self, db: AsyncSession, user: dict[str, Any], client_id: int, now: datetime) -> None:
        grants = await self.client_grants(db, user, client_id, now)
        if not any(BuyerService.can_approve(grant) for grant in grants):
            raise DealForbiddenError("Only the deal partner, director or a buyers.manage member edits the exclusion list")

    async def exclusions(self, db: AsyncSession, client_id: int) -> list[dict[str, Any]]:
        await self._company(db, client_id)
        rows = (
            await db.execute(
                select(ClientExclusion, Company.name)
                .join(Company, Company.id == ClientExclusion.company_id)
                .where(ClientExclusion.client_id == client_id)
                .order_by(Company.name)
            )
        ).all()
        return [{"company_id": row.company_id, "name": name, "added_at": row.added_at} for row, name in rows]

    async def add_exclusion(self, db: AsyncSession, client_id: int, company_id: int, context: AuditContext) -> dict[str, Any]:
        assert context.user_id is not None
        await self._company(db, client_id)
        await self._company(db, company_id)
        exists = (
            await db.execute(
                select(ClientExclusion.id).where(
                    ClientExclusion.client_id == client_id, ClientExclusion.company_id == company_id
                )
            )
        ).first()
        if exists is None:
            db.add(
                ClientExclusion(
                    client_id=client_id, company_id=company_id, added_by=context.user_id, added_at=context.clock.now()
                )
            )
            self.audit.record(
                db,
                context,
                "client_exclusion.added",
                record_type="company",
                record_id=client_id,
                new_values={"company_id": company_id},
            )
            await db.commit()
        return next(row for row in await self.exclusions(db, client_id) if row["company_id"] == company_id)

    async def remove_exclusion(self, db: AsyncSession, client_id: int, company_id: int, context: AuditContext) -> None:
        await db.execute(
            delete(ClientExclusion).where(ClientExclusion.client_id == client_id, ClientExclusion.company_id == company_id)
        )
        self.audit.record(
            db,
            context,
            "client_exclusion.removed",
            record_type="company",
            record_id=client_id,
            new_values={"company_id": company_id},
        )
        await db.commit()

    async def buyer_roles(self, db: AsyncSession, contact_id: int, user: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
        """A contact's buyer status on deals, only those the reader is staffed on (AUTHZ-02 c5)."""
        visible = DealPolicy(now).visible(user, select(Mandate.id)).scalar_subquery()
        rows = (
            await db.execute(
                select(DealBuyer, Mandate.code_name)
                .join(Mandate, Mandate.id == DealBuyer.mandate_id)
                .where(DealBuyer.contact_id == contact_id, Mandate.id.in_(visible))
                .order_by(Mandate.code_name)
            )
        ).all()
        return [
            {"mandate_id": row.mandate_id, "code_name": code, "company_id": row.company_id, "status": row.status}
            for row, code in rows
        ]


class BuyerService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    # Suggest and add (BUY-01)

    async def suggestions(
        self,
        db: AsyncSession,
        grant: DealGrant,
        ev_ebitda: Decimal | None = None,
        stake: SuggestStake | None = None,
    ) -> list[dict[str, Any]]:
        """Companies with an investor profile, ranked by how many criteria fit the target's sector, geography and size."""
        mandate = grant.mandate
        subject = await db.get(Company, mandate.target_id or mandate.client_id)
        assert subject is not None
        country_id = subject.country_id
        ev_millions = mandate.estimated_ev / 1000
        listed = select(DealBuyer.company_id).where(DealBuyer.mandate_id == mandate.id)
        rows = (
            await db.execute(
                select(InvestorProfile, Company)
                .join(Company, Company.id == InvestorProfile.company_id)
                .where(
                    InvestorProfile.criteria_updated_at.is_not(None),
                    Company.id.not_in(listed),
                    Company.id.not_in([cid for cid in (mandate.client_id, mandate.target_id) if cid is not None]),
                    *_profile_filters(ev_ebitda, stake),
                )
            )
        ).all()
        criteria: dict[int, set[tuple[str, int]]] = {}
        for company_id, kind, value_id in (
            await db.execute(
                select(InvestorCriterion.company_id, InvestorCriterion.kind, InvestorCriterion.value_id).where(
                    InvestorCriterion.company_id.in_([company.id for _, company in rows])
                )
            )
        ).all():
            criteria.setdefault(company_id, set()).add((kind, value_id))
        ranked = []
        for profile, company in rows:
            own = criteria.get(company.id, set())
            matched = []
            if ("sector", mandate.sector_id) in own:
                matched.append("sector")
            if ("country", country_id) in own:
                matched.append("geography")
            low, high = profile.ticket_min, profile.ticket_max
            if (
                (low is not None or high is not None)
                and (low is None or low <= ev_millions)
                and (high is None or ev_millions <= high)
            ):
                matched.append("size")
            if matched:
                ranked.append(
                    {
                        "company_id": company.id,
                        "name": company.name,
                        "type": company.type,
                        "score": len(matched),
                        "matched": matched,
                    }
                )
        ranked.sort(key=lambda row: (-row["score"], row["name"]))
        return ranked

    async def _active_member(self, db: AsyncSession, mandate_id: int, user_id: int, now: datetime) -> bool:
        row = (
            await db.execute(
                select(DealTeamMember.id).where(
                    DealTeamMember.mandate_id == mandate_id,
                    DealTeamMember.user_id == user_id,
                    (DealTeamMember.expires_at.is_(None)) | (DealTeamMember.expires_at > now),
                )
            )
        ).first()
        return row is not None

    async def _check_contact(self, db: AsyncSession, contact_id: int | None) -> None:
        if contact_id is None:
            return
        contact = await db.get(Contact, contact_id)
        if contact is None:
            raise ValidationError(f"Contact {contact_id} does not exist", field="contact_id")
        if contact.do_not_contact:
            raise ValidationError(
                f"{contact.first_name} {contact.last_name} is marked Do not contact and cannot be used for buyer outreach",
                field="contact_id",
            )

    async def _warnings(self, db: AsyncSession, mandate: Mandate, company: Company, now: datetime) -> list[WarningReason]:
        reasons = []
        hits = await ConflictService().find_hits(db, mandate, [(company.id, "counterparty")], now)
        if hits:
            reasons.append(WarningReason.CONFLICT)
        excluded = (
            await db.execute(
                select(ClientExclusion.id).where(
                    ClientExclusion.client_id == mandate.client_id,
                    ClientExclusion.company_id.in_([member.id for member in await _group(db, company.id)]),
                )
            )
        ).first()
        if excluded is not None:
            reasons.append(WarningReason.CLIENT_EXCLUSION)
        return reasons

    async def add(self, db: AsyncSession, grant: DealGrant, values: BuyersAdd, context: AuditContext) -> dict[str, Any]:
        assert context.user_id is not None
        mandate = grant.mandate
        now = context.clock.now()
        for index, item in enumerate(values.items):
            if _blank(item.rationale):
                raise ValidationError("Give a rationale for every buyer", field=f"items.{index}.rationale")
            if not await self._active_member(db, mandate.id, item.owner_id, now):
                raise ValidationError("The owner must be on the deal team", field=f"items.{index}.owner_id")
            if await db.get(Company, item.company_id) is None:
                raise ValidationError(f"Company {item.company_id} does not exist", field=f"items.{index}.company_id")
            await self._check_contact(db, item.contact_id)
        listed = set((await db.execute(select(DealBuyer.company_id).where(DealBuyer.mandate_id == mandate.id))).scalars())
        added: list[int] = []
        skipped: list[int] = []
        warnings: list[dict[str, Any]] = []
        for item in values.items:
            if item.company_id in listed:
                skipped.append(item.company_id)
                continue
            company = await db.get(Company, item.company_id)
            assert company is not None
            reasons = await self._warnings(db, mandate, company, now)
            if reasons:
                warnings.extend({"company_id": company.id, "name": company.name, "reason": reason} for reason in reasons)
                if not values.confirm:
                    continue
            buyer = DealBuyer(
                mandate_id=mandate.id,
                company_id=item.company_id,
                owner_id=item.owner_id,
                rationale=item.rationale.strip(),
                added_by=context.user_id,
                added_at=now,
                status=BuyerStatus.LONG_LIST.value,
                status_changed_at=now,
                status_changed_by=context.user_id,
                last_activity_at=now,
                contact_id=item.contact_id,
            )
            db.add(buyer)
            await db.flush()
            listed.add(item.company_id)
            added.append(buyer.id)
            self.audit.record(
                db,
                context,
                "buyer.added",
                record_type="mandate",
                record_id=mandate.id,
                new_values={"buyer_id": buyer.id, "company_id": item.company_id, "warnings": [r.value for r in reasons]},
            )
        await db.commit()
        return {"added": added, "skipped": skipped, "warnings": warnings}

    # The grid (BUY-03)

    async def grid(self, db: AsyncSession, grant: DealGrant) -> dict[str, Any]:
        owner, changer = aliased(User), aliased(User)
        rows = (
            await db.execute(
                select(DealBuyer, Company, owner.name, changer.name, Contact, BuyerNda)
                .join(Company, Company.id == DealBuyer.company_id)
                .join(owner, owner.id == DealBuyer.owner_id)
                .join(changer, changer.id == DealBuyer.status_changed_by)
                .outerjoin(Contact, Contact.id == DealBuyer.contact_id)
                .outerjoin(BuyerNda, BuyerNda.buyer_id == DealBuyer.id)
                .where(DealBuyer.mandate_id == grant.mandate.id)
                .order_by(Company.name, DealBuyer.id)
            )
        ).all()
        buyers = [
            {
                "id": buyer.id,
                "company_id": company.id,
                "name": company.name,
                "type": company.type,
                "owner_id": buyer.owner_id,
                "owner_name": owner_name,
                "rationale": buyer.rationale,
                "contact_id": buyer.contact_id,
                "contact_name": f"{contact.first_name} {contact.last_name}" if contact else None,
                "approval": buyer.approval,
                "status": buyer.status,
                "status_changed_at": buyer.status_changed_at,
                "status_changed_by_name": changer_name,
                "decline_reason": buyer.decline_reason,
                "notes": buyer.notes,
                "nda": _nda(nda) if nda else None,
            }
            for buyer, company, owner_name, changer_name, contact, nda in rows
        ]
        funnel = {status.value: 0 for status in BuyerStatus}
        for row in buyers:
            funnel[row["status"]] += 1
        return {"buyers": buyers, "funnel": funnel, "can_approve": self.can_approve(grant)}

    @staticmethod
    def can_approve(grant: DealGrant) -> bool:
        return grant.can_manage_team or (grant.can_edit and has_permission(grant.user, Permission.BUYERS_MANAGE))

    async def _buyer(self, db: AsyncSession, grant: DealGrant, buyer_id: int) -> DealBuyer:
        buyer = await db.get(DealBuyer, buyer_id)
        if buyer is None or buyer.mandate_id != grant.mandate.id:
            raise ValidationError(f"Buyer {buyer_id} is not on this deal", field="buyer_id")
        return buyer

    async def update(
        self, db: AsyncSession, grant: DealGrant, buyer_id: int, values: BuyerUpdate, context: AuditContext
    ) -> dict[str, Any]:
        buyer = await self._buyer(db, grant, buyer_id)
        now = context.clock.now()
        changes = values.model_dump(exclude_unset=True)
        if "approval" in changes and not self.can_approve(grant):
            raise DealForbiddenError("Only the deal partner or director records the client's approval")
        if "owner_id" in changes and (
            values.owner_id is None or not await self._active_member(db, grant.mandate.id, values.owner_id, now)
        ):
            raise ValidationError("The owner must be on the deal team", field="owner_id")
        if "rationale" in changes and _blank(values.rationale):
            raise ValidationError("Give a rationale for the buyer", field="rationale")
        if "contact_id" in changes:
            await self._check_contact(db, values.contact_id)
        if values.approval == Approval.EXCLUDED and buyer.status not in NOT_APPROACHED:
            raise ValidationError("A buyer already approached cannot be excluded", field="approval")
        old = {field: getattr(buyer, field) for field in changes}
        for field, value in changes.items():
            setattr(buyer, field, value.strip() if field == "rationale" and value else value)
        if "approval" in changes and buyer.status in NOT_APPROACHED:
            approved = values.approval == Approval.APPROVED
            status = BuyerStatus.CLIENT_APPROVED if approved else BuyerStatus.LONG_LIST
            if buyer.status != status.value:
                assert context.user_id is not None
                buyer.status = status.value
                buyer.status_changed_at = now
                buyer.status_changed_by = context.user_id
        buyer.last_activity_at = now
        self.audit.record(
            db,
            context,
            "buyer.updated",
            record_type="mandate",
            record_id=grant.mandate.id,
            old_values={"buyer_id": buyer.id, **{k: v for k, v in old.items() if k != "notes"}},
            new_values={"buyer_id": buyer.id, **{k: v for k, v in changes.items() if k != "notes"}},
        )
        await db.commit()
        return next(row for row in (await self.grid(db, grant))["buyers"] if row["id"] == buyer.id)

    def _check_status(self, buyer: DealBuyer, status: BuyerStatus, nda: BuyerNda | None) -> None:
        if status in (BuyerStatus.LONG_LIST, BuyerStatus.DECLINED):
            return
        if status == BuyerStatus.CLIENT_APPROVED:
            raise ValidationError("Client approved follows from the client's approval: record it in Approval", field="status")
        if status == BuyerStatus.NDA_SIGNED:
            raise ValidationError("NDA signed follows from the NDA's signed date: log it on the NDA", field="status")
        if buyer.approval != Approval.APPROVED.value:
            raise ValidationError("Only buyers the client approved can be contacted", field="status")
        if status in AFTER_NDA and (nda is None or nda.signed_date is None):
            raise ValidationError(f"{status.value.replace('_', ' ').capitalize()} needs a signed NDA first", field="status")

    async def set_status(
        self, db: AsyncSession, grant: DealGrant, values: StatusChange, context: AuditContext
    ) -> dict[str, Any]:
        """One date for the whole selection; nothing changes unless every buyer may move."""
        assert context.user_id is not None
        if values.status == BuyerStatus.DECLINED and values.decline_reason is None:
            raise ValidationError("Give the reason the buyer declined", field="decline_reason")
        now = context.clock.now()
        rows = []
        for buyer_id in dict.fromkeys(values.buyer_ids):
            buyer = await self._buyer(db, grant, buyer_id)
            nda = (await db.execute(select(BuyerNda).where(BuyerNda.buyer_id == buyer.id))).scalar_one_or_none()
            self._check_status(buyer, values.status, nda)
            rows.append(buyer)
        for buyer in rows:
            old = buyer.status
            buyer.status = values.status.value
            buyer.decline_reason = (
                values.decline_reason.value if values.status == BuyerStatus.DECLINED and values.decline_reason else None
            )
            buyer.status_changed_at = now
            buyer.status_changed_by = context.user_id
            buyer.last_activity_at = now
            self.audit.record(
                db,
                context,
                "buyer.status_changed",
                record_type="mandate",
                record_id=grant.mandate.id,
                old_values={"buyer_id": buyer.id, "status": old},
                new_values={"buyer_id": buyer.id, "status": buyer.status, "decline_reason": buyer.decline_reason},
            )
        await db.commit()
        return await self.grid(db, grant)

    # NDAs (BUY-04)

    async def set_nda(
        self, db: AsyncSession, grant: DealGrant, buyer_id: int, values: NdaUpdate, context: AuditContext
    ) -> dict[str, Any]:
        assert context.user_id is not None
        buyer = await self._buyer(db, grant, buyer_id)
        if buyer.approval != Approval.APPROVED.value:
            raise ValidationError("Only buyers the client approved can be sent an NDA", field="sent_date")
        if values.signed_date is not None and values.sent_date is None:
            raise ValidationError("Log the date the NDA was sent", field="sent_date")
        now = context.clock.now()
        nda = (await db.execute(select(BuyerNda).where(BuyerNda.buyer_id == buyer.id))).scalar_one_or_none()
        if nda is None:
            nda = BuyerNda(buyer_id=buyer.id)
            db.add(nda)
        data = values.model_dump(mode="python")
        data["document_url"] = str(values.document_url) if values.document_url else None
        if data["sent_date"] != nda.sent_date:
            nda.reminded_at = None
        for field, value in data.items():
            setattr(nda, field, value)
        position = ORDER.index(BuyerStatus(buyer.status))
        target: BuyerStatus | None = None
        if nda.signed_date is not None and position < ORDER.index(BuyerStatus.NDA_SIGNED):
            target = BuyerStatus.NDA_SIGNED
        elif nda.signed_date is None and nda.sent_date is not None and position < ORDER.index(BuyerStatus.NDA_SENT):
            target = BuyerStatus.NDA_SENT
        elif nda.signed_date is None and buyer.status == BuyerStatus.NDA_SIGNED.value:
            target = BuyerStatus.NDA_SENT if nda.sent_date else BuyerStatus.CONTACTED
        if target is not None:
            buyer.status = target.value
            buyer.decline_reason = None
            buyer.status_changed_at = now
            buyer.status_changed_by = context.user_id
        buyer.last_activity_at = now
        if nda.signed_date is not None and (values.standstill_end or values.non_solicit_end):
            profile = await InvestorProfileService()._profile_row(db, buyer.company_id)
            if values.standstill_end:
                profile.standstill_end = values.standstill_end
            if values.non_solicit_end:
                profile.non_solicit_end = values.non_solicit_end
        self.audit.record(
            db,
            context,
            "buyer.nda_updated",
            record_type="mandate",
            record_id=grant.mandate.id,
            new_values={"buyer_id": buyer.id, **values.model_dump(mode="json")},
        )
        await db.commit()
        return _nda(nda)

    # Export (BUY-02)

    async def export(self, db: AsyncSession, grant: DealGrant, context: AuditContext) -> bytes:
        """The client's copy: buyer, type, rationale, contact. Internal notes never leave the CRM."""
        grid = await self.grid(db, grant)
        book = Workbook()
        sheet = book.active
        assert sheet is not None
        sheet.title = "Buyers"
        sheet.append(safe_row(["Buyer", "Type", "Rationale", "Contact"]))
        for row in grid["buyers"]:
            if row["approval"] == Approval.EXCLUDED.value:
                continue
            sheet.append(
                safe_row([row["name"], TYPE_LABELS.get(row["type"], row["type"]), row["rationale"], row["contact_name"] or ""])
            )
        self.audit.record(
            db,
            context,
            "export",
            record_type="mandate",
            record_id=grant.mandate.id,
            new_values={"kind": "buyer_list", "rows": sheet.max_row - 1},
        )
        await db.commit()
        out = io.BytesIO()
        book.save(out)
        return out.getvalue()


def _nda(nda: BuyerNda) -> dict[str, Any]:
    return {
        "sent_date": nda.sent_date,
        "markup_received_date": nda.markup_received_date,
        "agreed_date": nda.agreed_date,
        "signed_date": nda.signed_date,
        "document_url": nda.document_url,
        "standstill_end": nda.standstill_end,
        "non_solicit_end": nda.non_solicit_end,
    }


async def _last_logged_activity(db: AsyncSession, buyer: DealBuyer, now: datetime) -> datetime | None:
    """The latest call, meeting or email logged on the buyer company or its contact (BUY-03 c5)."""
    linked = (ActivityLink.record_type == "company") & (ActivityLink.record_id == buyer.company_id)
    if buyer.contact_id is not None:
        linked = linked | ((ActivityLink.record_type == "contact") & (ActivityLink.record_id == buyer.contact_id))
    return (
        await db.execute(
            select(func.max(Activity.occurred_at))
            .join(ActivityLink, ActivityLink.activity_id == Activity.id)
            .where(linked, Activity.deleted_at.is_(None), Activity.occurred_at <= now)
        )
    ).scalar_one_or_none()


class BuyerReminders:
    def __init__(self, notifications: NotificationService | None = None) -> None:
        self.notifications = notifications or NotificationService(LoggingEmailSender())

    async def run(self, db: AsyncSession, now: datetime) -> None:
        idle = (
            await db.execute(
                select(DealBuyer, Mandate, User)
                .join(Mandate, Mandate.id == DealBuyer.mandate_id)
                .join(User, User.id == DealBuyer.owner_id)
                .where(
                    Mandate.closed_at.is_(None),
                    Mandate.stage.in_([stage.value for stage in ACTIVE_PHASES]),
                    DealBuyer.status != BuyerStatus.DECLINED.value,
                    DealBuyer.approval != Approval.EXCLUDED.value,
                    DealBuyer.last_activity_at <= now - BUYER_IDLE_AFTER,
                )
            )
        ).all()
        for buyer, mandate, owner in idle:
            last = max(buyer.last_activity_at, await _last_logged_activity(db, buyer, now) or buyer.last_activity_at)
            if last > now - BUYER_IDLE_AFTER or (buyer.idle_reminded_at is not None and buyer.idle_reminded_at >= last):
                continue
            await self._remind(
                db,
                owner,
                mandate,
                EventKind.BUYER_IDLE,
                f"{mandate.code_name}: a buyer has had no activity for 14 days",
                f"One of your buyers on {mandate.code_name} has had no activity for 14 days.",
                now,
            )
            buyer.idle_reminded_at = now
        pending = (
            await db.execute(
                select(BuyerNda, DealBuyer, Mandate, User)
                .join(DealBuyer, DealBuyer.id == BuyerNda.buyer_id)
                .join(Mandate, Mandate.id == DealBuyer.mandate_id)
                .join(User, User.id == DealBuyer.owner_id)
                .where(
                    Mandate.closed_at.is_(None),
                    BuyerNda.sent_date.is_not(None),
                    BuyerNda.signed_date.is_(None),
                    BuyerNda.reminded_at.is_(None),
                    BuyerNda.sent_date < now.date() - timedelta(days=NDA_PENDING_DAYS),
                    DealBuyer.status != BuyerStatus.DECLINED.value,
                )
            )
        ).all()
        for nda, _, mandate, owner in pending:
            await self._remind(
                db,
                owner,
                mandate,
                EventKind.NDA_PENDING,
                f"{mandate.code_name}: NDA pending for more than {NDA_PENDING_DAYS} days",
                f"An NDA you own on {mandate.code_name} was sent more than {NDA_PENDING_DAYS} days ago and is not signed.",
                now,
            )
            nda.reminded_at = now
        await db.commit()
        await self.notifications.flush_emails()

    async def _remind(
        self, db: AsyncSession, owner: User, mandate: Mandate, kind: EventKind, title: str, body: str, now: datetime
    ) -> None:
        # Code name only: a deal notification never names the client or a buyer.
        await self.notifications.add(
            db,
            Message(
                user_id=owner.id,
                email=owner.email,
                kind=kind.value,
                title=title,
                body=body,
                link=f"/deals/{mandate.id}",
                mandate_id=mandate.id,
            ),
            now,
        )
