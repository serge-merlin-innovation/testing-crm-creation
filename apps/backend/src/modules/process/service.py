"""The bidding process: offers and their comparison (BUY-05), templates (ADM-07), process letters (BUY-06),
the funnel (BUY-07) and the client status report (REP-05)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity.models import Activity, ActivityLink
from ..activity.schemas import ActivityType, RecordType
from ..audit.service import AuditContext, AuditService, audit_export
from ..buyer.models import BuyerNda, DealBuyer
from ..buyer.schemas import Approval, BuyerStatus
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..company.models import Company, FinancialFigure
from ..company.schemas import FigureSource, Metric
from ..contact.models import Contact
from ..mandate.models import Milestone
from ..mandate.policy import DealGrant
from ..notification.ports import EmailSender, SentEmail
from ..task.models import Task
from ..task.service import read as task_read
from ..user.models import User
from .documents import FUNNEL_STEPS, conversion, implied_multiple, pdf, render, unknown_fields
from .models import BidDeadline, DocumentTemplate, GeneratedDocument, Offer
from .schemas import (
    BidDeadlines,
    ExclusionReason,
    LetterRequest,
    OfferCreate,
    OfferRound,
    TemplateKind,
    TemplateWrite,
)

ORDER = list(BuyerStatus)
# Statuses at or past each funnel step. Declined buyers count as approached only (decision 46).
STEP_FLOOR = {
    "nda": BuyerStatus.NDA_SIGNED,
    "im": BuyerStatus.IM_SENT,
    "offers": BuyerStatus.INDICATIVE_OFFER,
    "binding": BuyerStatus.BINDING_OFFER,
}
FUNNEL_LABELS = {
    "en": {"approached": "Approached", "nda": "NDA signed", "im": "IM sent", "offers": "Offers", "binding": "Binding offers"},
    "fr": {"approached": "Approchés", "nda": "NDA signé", "im": "IM envoyé", "offers": "Offres", "binding": "Offres fermes"},
    "nl": {
        "approached": "Benaderd",
        "nda": "NDA getekend",
        "im": "IM verstuurd",
        "offers": "Biedingen",
        "binding": "Bindende biedingen",
    },
}
REPORT_WORDS = {
    "en": {"planned": "planned", "actual": "actual", "open": "open", "late": "late", "none": "None"},
    "fr": {"planned": "prévu", "actual": "réalisé", "open": "en cours", "late": "en retard", "none": "Aucune"},
    "nl": {"planned": "gepland", "actual": "gerealiseerd", "open": "open", "late": "te laat", "none": "Geen"},
}
# Used when the firm has not written its own report wording in the client's language yet.
DEFAULT_REPORT = {
    "en": (
        "Status report {{code_name}}",
        "Status on {{date}}\n\nProcess funnel\n{{funnel}}\n\nTimeline vs plan\n{{timeline}}\n\nNext steps\n{{next_steps}}",
    ),
    "fr": (
        "Rapport d'avancement {{code_name}}",
        "Situation au {{date}}\n\nEntonnoir du processus\n{{funnel}}\n\n"
        "Calendrier et planning\n{{timeline}}\n\nProchaines étapes\n{{next_steps}}",
    ),
    "nl": (
        "Statusrapport {{code_name}}",
        "Stand van zaken op {{date}}\n\nProcestrechter\n{{funnel}}\n\n"
        "Tijdlijn versus planning\n{{timeline}}\n\nVolgende stappen\n{{next_steps}}",
    ),
}
EXCLUSION_MESSAGES = {
    ExclusionReason.NOT_ACTIVE: "The buyer is not active (not approved by the client, or declined)",
    ExclusionReason.NO_SIGNED_NDA: "The letter references the IM and the buyer has not signed an NDA",
    ExclusionReason.OPTED_OUT: "The contact opted out of mailings",
    ExclusionReason.DO_NOT_CONTACT: "The contact is marked Do not contact",
    ExclusionReason.NO_CONTACT: "The buyer has no contact",
    ExclusionReason.NO_EMAIL: "The contact has no email address",
    ExclusionReason.NO_TEMPLATE_LANGUAGE: "The template has no version in the contact's language",
}


def _offer_read(offer: Offer, buyer_name: str, entered_by: str, ebitda: Decimal | None) -> dict[str, Any]:
    return {
        "id": offer.id,
        "buyer_id": offer.buyer_id,
        "buyer_name": buyer_name,
        "round": offer.round,
        "version": offer.version,
        "ev": offer.ev,
        "equity_value": offer.equity_value,
        "cash_pct": offer.cash_pct,
        "earn_out_pct": offer.earn_out_pct,
        "vendor_loan_pct": offer.vendor_loan_pct,
        "rollover_pct": offer.rollover_pct,
        "conditions": offer.conditions,
        "financing_certainty": offer.financing_certainty,
        "received_at": offer.received_at,
        "late": offer.late,
        "entered_by_name": entered_by,
        "entered_at": offer.entered_at,
        "ev_ebitda": implied_multiple(offer.ev, ebitda),
    }


def _template_read(template: DocumentTemplate, by: str | None) -> dict[str, Any]:
    return {
        "id": template.id,
        "kind": template.kind,
        "name": template.name,
        "language": template.language,
        "subject": template.subject,
        "body": template.body,
        "references_im": template.references_im,
        "updated_at": template.updated_at,
        "updated_by_name": by,
    }


def _template_snapshot(template: DocumentTemplate) -> dict[str, Any]:
    return {
        "kind": template.kind,
        "name": template.name,
        "language": template.language,
        "subject": template.subject,
        "body": template.body,
        "references_im": template.references_im,
    }


async def _log_activity(
    db: AsyncSession, author_id: int, now: datetime, note: str, participants: list[str], links: list[tuple[str, int]]
) -> None:
    activity = Activity(
        type=ActivityType.EMAIL.value,
        occurred_at=now,
        note=note,
        participants=participants,
        author_id=author_id,
        created_at=now,
    )
    db.add(activity)
    await db.flush()
    db.add_all(ActivityLink(activity_id=activity.id, record_type=kind, record_id=rid) for kind, rid in dict.fromkeys(links))


class OfferService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def _deadlines(self, db: AsyncSession, mandate_id: int) -> BidDeadline | None:
        return (await db.execute(select(BidDeadline).where(BidDeadline.mandate_id == mandate_id))).scalar_one_or_none()

    async def ebitda(self, db: AsyncSession, company_id: int | None) -> tuple[Decimal | None, int | None]:
        """The target's EBITDA of its latest year, a manual override winning over the NBB import."""
        if company_id is None:
            return None, None
        rows = (
            await db.execute(
                select(FinancialFigure)
                .where(FinancialFigure.company_id == company_id, FinancialFigure.metric == Metric.EBITDA.value)
                .order_by(FinancialFigure.year.desc())
            )
        ).scalars()
        latest: dict[str, FinancialFigure] = {}
        year: int | None = None
        for figure in rows:
            if year is None:
                year = figure.year
            if figure.year != year:
                break
            latest[figure.source] = figure
        chosen = latest.get(FigureSource.MANUAL.value) or latest.get(FigureSource.NBB.value)
        return (chosen.value, year) if chosen else (None, None)

    async def comparison(self, db: AsyncSession, grant: DealGrant) -> dict[str, Any]:
        mandate = grant.mandate
        ebitda, year = await self.ebitda(db, mandate.target_id)
        rows = (
            await db.execute(
                select(Offer, Company.name, User.name)
                .join(DealBuyer, DealBuyer.id == Offer.buyer_id)
                .join(Company, Company.id == DealBuyer.company_id)
                .join(User, User.id == Offer.entered_by)
                .where(Offer.mandate_id == mandate.id)
                .order_by(Offer.entered_at.desc(), Offer.id.desc())
            )
        ).all()
        history = [_offer_read(offer, name, by, ebitda) for offer, name, by in rows]
        latest: dict[tuple[int, str], dict[str, Any]] = {}
        for item in history:
            latest.setdefault((item["buyer_id"], item["round"]), item)
        bids = sorted(latest.values(), key=lambda item: (-item["ev"], item["buyer_name"]))
        deadlines = await self._deadlines(db, mandate.id)
        return {
            "ebitda": ebitda,
            "ebitda_year": year,
            "bids": bids,
            "history": history,
            "deadlines": {
                "indicative_at": deadlines.indicative_at if deadlines else None,
                "binding_at": deadlines.binding_at if deadlines else None,
            },
        }

    async def set_deadlines(
        self, db: AsyncSession, grant: DealGrant, values: BidDeadlines, context: AuditContext
    ) -> dict[str, Any]:
        row = await self._deadlines(db, grant.mandate.id)
        if row is None:
            row = BidDeadline(mandate_id=grant.mandate.id)
            db.add(row)
        old = {"indicative_at": row.indicative_at, "binding_at": row.binding_at}
        row.indicative_at, row.binding_at = values.indicative_at, values.binding_at
        self.audit.record(
            db,
            context,
            "bid_deadlines.set",
            record_type="mandate",
            record_id=grant.mandate.id,
            old_values={key: value.isoformat() if value else None for key, value in old.items()},
            new_values=values.model_dump(mode="json"),
        )
        await db.commit()
        return values.model_dump()

    async def add(self, db: AsyncSession, grant: DealGrant, values: OfferCreate, context: AuditContext) -> dict[str, Any]:
        assert context.user_id is not None
        mandate = grant.mandate
        buyer = await db.get(DealBuyer, values.buyer_id)
        if buyer is None or buyer.mandate_id != mandate.id:
            raise ValidationError("The buyer is not on this deal", field="buyer_id")
        now = context.clock.now()
        received = values.received_at or now
        deadlines = await self._deadlines(db, mandate.id)
        deadline = None
        if deadlines is not None:
            deadline = deadlines.indicative_at if values.round == OfferRound.INDICATIVE else deadlines.binding_at
        version = (
            await db.execute(
                select(func.coalesce(func.max(Offer.version), 0)).where(
                    Offer.buyer_id == buyer.id, Offer.round == values.round.value
                )
            )
        ).scalar_one() + 1
        offer = Offer(
            mandate_id=mandate.id,
            buyer_id=buyer.id,
            round=values.round.value,
            version=version,
            ev=values.ev,
            equity_value=values.equity_value,
            cash_pct=values.cash_pct,
            earn_out_pct=values.earn_out_pct,
            vendor_loan_pct=values.vendor_loan_pct,
            rollover_pct=values.rollover_pct,
            conditions=values.conditions.strip(),
            financing_certainty=values.financing_certainty.value,
            received_at=received,
            late=deadline is not None and received > deadline,
            entered_by=context.user_id,
            entered_at=now,
        )
        db.add(offer)
        await db.flush()
        self.audit.record(
            db,
            context,
            "offer.added",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"offer_id": offer.id, "buyer_id": buyer.id, "version": version, **values.model_dump(mode="json")},
        )
        await db.commit()
        company = await db.get(Company, buyer.company_id)
        user = await db.get(User, context.user_id)
        assert company is not None
        assert user is not None
        ebitda, _ = await self.ebitda(db, mandate.target_id)
        return _offer_read(offer, company.name, user.name, ebitda)


class TemplateService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def list(self, db: AsyncSession) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(DocumentTemplate, User.name)
                .outerjoin(User, User.id == DocumentTemplate.updated_by)
                .order_by(DocumentTemplate.kind, DocumentTemplate.name, DocumentTemplate.language)
            )
        ).all()
        return [_template_read(template, by) for template, by in rows]

    @staticmethod
    def _check(values: TemplateWrite) -> None:
        for field in ("subject", "body"):
            unknown = unknown_fields(getattr(values, field))
            if unknown:
                raise ValidationError(f"Unknown merge fields: {', '.join(unknown)}", field=field)

    async def create(self, db: AsyncSession, values: TemplateWrite, context: AuditContext) -> dict[str, Any]:
        assert context.user_id is not None
        self._check(values)
        clash = await db.execute(
            select(DocumentTemplate.id).where(
                DocumentTemplate.kind == values.kind.value,
                func.lower(DocumentTemplate.name) == values.name.strip().lower(),
                DocumentTemplate.language == values.language.value,
            )
        )
        if clash.first() is not None:
            raise ValidationError("This template already has a version in that language", field="language")
        template = DocumentTemplate(
            kind=values.kind.value,
            name=values.name.strip(),
            language=values.language.value,
            subject=values.subject,
            body=values.body,
            references_im=values.references_im,
            updated_at=context.clock.now(),
            updated_by=context.user_id,
        )
        db.add(template)
        await db.flush()
        self.audit.record(
            db,
            context,
            "template.created",
            record_type="template",
            record_id=template.id,
            new_values=_template_snapshot(template),
        )
        await db.commit()
        user = await db.get(User, context.user_id)
        return _template_read(template, user.name if user else None)

    async def update(self, db: AsyncSession, template_id: int, values: TemplateWrite, context: AuditContext) -> dict[str, Any]:
        assert context.user_id is not None
        self._check(values)
        template = await db.get(DocumentTemplate, template_id)
        if template is None:
            raise ResourceNotFoundError("Template not found")
        old = _template_snapshot(template)
        template.kind, template.name, template.language = values.kind.value, values.name.strip(), values.language.value
        template.subject, template.body, template.references_im = values.subject, values.body, values.references_im
        template.updated_at, template.updated_by = context.clock.now(), context.user_id
        self.audit.record(
            db,
            context,
            "template.updated",
            record_type="template",
            record_id=template.id,
            old_values=old,
            new_values=_template_snapshot(template),
        )
        await db.commit()
        user = await db.get(User, context.user_id)
        return _template_read(template, user.name if user else None)

    async def versions(self, db: AsyncSession, kind: TemplateKind, name: str) -> dict[str, DocumentTemplate]:
        rows = (
            await db.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.kind == kind.value, func.lower(DocumentTemplate.name) == name.strip().lower()
                )
            )
        ).scalars()
        return {row.language: row for row in rows}


class ProcessService:
    def __init__(self, sender: EmailSender, audit: AuditService | None = None) -> None:
        self.sender = sender
        self.audit = audit or AuditService()
        self.templates = TemplateService(self.audit)

    # The funnel (BUY-07)

    async def funnel(self, db: AsyncSession, grant: DealGrant) -> dict[str, Any]:
        mandate_id = grant.mandate.id
        buyers = list((await db.execute(select(DealBuyer).where(DealBuyer.mandate_id == mandate_id))).scalars())
        offered = {
            (buyer_id, round_)
            for buyer_id, round_ in (
                await db.execute(select(Offer.buyer_id, Offer.round).where(Offer.mandate_id == mandate_id).distinct())
            ).tuples()
        }
        counts = dict.fromkeys(FUNNEL_STEPS, 0)
        for buyer in buyers:
            status = BuyerStatus(buyer.status)
            if status == BuyerStatus.LONG_LIST:
                continue
            counts["approached"] += 1
            position = ORDER.index(status) if status != BuyerStatus.DECLINED else -1
            for step, floor in STEP_FLOOR.items():
                reached = position >= ORDER.index(floor)
                if step == "offers":
                    reached = reached or any(b == buyer.id for b, _ in offered)
                if step == "binding":
                    reached = reached or (buyer.id, OfferRound.BINDING.value) in offered
                if reached:
                    counts[step] += 1
        # An offer implies the earlier steps, even for a buyer who later declined.
        rates = conversion(counts[step] for step in FUNNEL_STEPS)
        steps = [
            {"key": step, "count": counts[step], "conversion_pct": rate} for step, rate in zip(FUNNEL_STEPS, rates, strict=True)
        ]
        return {"code_name": grant.mandate.code_name, "steps": steps}

    @staticmethod
    def funnel_text(funnel: dict[str, Any], language: str) -> str:
        labels = FUNNEL_LABELS[language]
        lines = []
        for step in funnel["steps"]:
            rate = f" ({step['conversion_pct']}%)" if step["conversion_pct"] is not None else ""
            lines.append(f"{labels[step['key']]}: {step['count']}{rate}")
        return "\n".join(lines)

    async def funnel_pdf(self, db: AsyncSession, grant: DealGrant, context: AuditContext) -> bytes:
        funnel = await self.funnel(db, grant)
        audit_export(
            db,
            context,
            "funnel",
            record_type="mandate",
            record_id=grant.mandate.id,
            filters={"mandate_id": grant.mandate.id},
            rows=len(funnel["steps"]),
        )
        await db.commit()
        return pdf(f"{grant.mandate.code_name} - funnel", self.funnel_text(funnel, "en"))

    # Process letters (BUY-06)

    async def send_letters(
        self, db: AsyncSession, grant: DealGrant, values: LetterRequest, context: AuditContext
    ) -> dict[str, Any]:
        assert context.user_id is not None
        mandate = grant.mandate
        versions = await self.templates.versions(db, TemplateKind.LETTER, values.template_name)
        if not versions:
            raise ValidationError("No letter template with that name", field="template_name")
        references_im = any(version.references_im for version in versions.values())
        now = context.clock.now()
        sent: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for buyer_id in dict.fromkeys(values.buyer_ids):
            row = (
                await db.execute(
                    select(DealBuyer, Company, Contact, BuyerNda)
                    .join(Company, Company.id == DealBuyer.company_id)
                    .outerjoin(Contact, Contact.id == DealBuyer.contact_id)
                    .outerjoin(BuyerNda, BuyerNda.buyer_id == DealBuyer.id)
                    .where(DealBuyer.id == buyer_id, DealBuyer.mandate_id == mandate.id)
                )
            ).first()
            if row is None:
                raise ValidationError(f"Buyer {buyer_id} is not on this deal", field="buyer_ids")
            buyer, company, contact, nda = row
            reason = self._exclusion(buyer, contact, nda, references_im, versions)
            if reason is not None:
                excluded.append(
                    {"buyer_id": buyer.id, "buyer_name": company.name, "reason": reason, "message": EXCLUSION_MESSAGES[reason]}
                )
                continue
            assert contact is not None
            assert contact.email
            template = versions[contact.language]
            fields = {
                "salutation": contact.salutation or "",
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "contact_name": f"{contact.first_name} {contact.last_name}",
                "buyer_name": company.name,
                "code_name": mandate.code_name,
                "stage": mandate.stage,
                "date": now.date().isoformat(),
            }
            subject, body = render(template.subject, fields), render(template.body, fields)
            document = GeneratedDocument(
                mandate_id=mandate.id,
                kind=TemplateKind.LETTER.value,
                language=contact.language,
                subject=subject,
                body=body,
                created_by=context.user_id,
                created_at=now,
                template_id=template.id,
                buyer_id=buyer.id,
                contact_id=contact.id,
            )
            db.add(document)
            await db.flush()
            await _log_activity(
                db,
                context.user_id,
                now,
                f"Process letter sent: {subject}\n\n{body}",
                [fields["contact_name"]],
                [
                    (RecordType.MANDATE.value, mandate.id),
                    (RecordType.CONTACT.value, contact.id),
                    (RecordType.COMPANY.value, company.id),
                ],
            )
            buyer.last_activity_at = now
            await self.sender.send(SentEmail(to=contact.email, subject=subject, body=body))
            sent.append(
                {
                    "buyer_id": buyer.id,
                    "buyer_name": company.name,
                    "contact_name": fields["contact_name"],
                    "language": contact.language,
                    "subject": subject,
                    "body": body,
                    "document_id": document.id,
                }
            )
        self.audit.record(
            db,
            context,
            "letter.sent",
            record_type="mandate",
            record_id=mandate.id,
            new_values={
                "template": values.template_name,
                "sent": [item["buyer_id"] for item in sent],
                "excluded": {str(item["buyer_id"]): item["reason"].value for item in excluded},
            },
        )
        await db.commit()
        return {"sent": sent, "excluded": excluded}

    @staticmethod
    def _exclusion(
        buyer: DealBuyer,
        contact: Contact | None,
        nda: BuyerNda | None,
        references_im: bool,
        versions: dict[str, DocumentTemplate],
    ) -> ExclusionReason | None:
        if buyer.approval != Approval.APPROVED.value or buyer.status == BuyerStatus.DECLINED.value:
            return ExclusionReason.NOT_ACTIVE
        if references_im and (nda is None or nda.signed_date is None):
            return ExclusionReason.NO_SIGNED_NDA
        if contact is None:
            return ExclusionReason.NO_CONTACT
        if contact.marketing_opt_out:
            return ExclusionReason.OPTED_OUT
        if contact.do_not_contact:
            return ExclusionReason.DO_NOT_CONTACT
        if not contact.email:
            return ExclusionReason.NO_EMAIL
        if contact.language not in versions:
            return ExclusionReason.NO_TEMPLATE_LANGUAGE
        return None

    # The client status report (REP-05)

    async def status_report(
        self, db: AsyncSession, grant: DealGrant, template_name: str, context: AuditContext
    ) -> tuple[GeneratedDocument, bytes]:
        """Funnel, timeline vs plan and next steps only: never notes, buyer names, offers or fees."""
        assert context.user_id is not None
        mandate = grant.mandate
        client = await db.get(Company, mandate.client_id)
        assert client is not None
        language = client.language
        now = context.clock.now()
        today = now.date()
        words = REPORT_WORDS[language]
        milestones = list(
            (
                await db.execute(
                    select(Milestone).where(Milestone.mandate_id == mandate.id).order_by(Milestone.planned_date, Milestone.id)
                )
            ).scalars()
        )
        timeline = []
        next_steps = []
        for milestone in milestones:
            if milestone.actual_date is not None:
                timeline.append(
                    f"{milestone.name}: {words['planned']} {milestone.planned_date.isoformat()}, "
                    f"{words['actual']} {milestone.actual_date.isoformat()}"
                )
            else:
                late = f" ({words['late']})" if milestone.planned_date < today else ""
                timeline.append(
                    f"{milestone.name}: {words['planned']} {milestone.planned_date.isoformat()}, {words['open']}{late}"
                )
                next_steps.append(f"{milestone.planned_date.isoformat()}: {milestone.name}")
        fields = {
            "code_name": mandate.code_name,
            "stage": mandate.stage,
            "date": today.isoformat(),
            "funnel": self.funnel_text(await self.funnel(db, grant), language),
            "timeline": "\n".join(timeline) or words["none"],
            "next_steps": "\n".join(next_steps) or words["none"],
        }
        versions = await self.templates.versions(db, TemplateKind.REPORT, template_name)
        template = versions.get(language)
        subject_text, body_text = (template.subject, template.body) if template else DEFAULT_REPORT[language]
        subject, body = render(subject_text, fields), render(body_text, fields)
        document = GeneratedDocument(
            mandate_id=mandate.id,
            kind=TemplateKind.REPORT.value,
            language=language,
            subject=subject,
            body=body,
            created_by=context.user_id,
            created_at=now,
            template_id=template.id if template else None,
        )
        db.add(document)
        await db.flush()
        await _log_activity(
            db, context.user_id, now, f"Client status report generated: {subject}", [], [(RecordType.MANDATE.value, mandate.id)]
        )
        self.audit.record(
            db,
            context,
            "report.generated",
            record_type="mandate",
            record_id=mandate.id,
            new_values={"document_id": document.id, "language": language},
        )
        await db.commit()
        return document, pdf(subject, body)

    async def documents(self, db: AsyncSession, grant: DealGrant) -> list[GeneratedDocument]:
        return list(
            (
                await db.execute(
                    select(GeneratedDocument)
                    .where(GeneratedDocument.mandate_id == grant.mandate.id)
                    .order_by(GeneratedDocument.created_at.desc(), GeneratedDocument.id.desc())
                )
            ).scalars()
        )

    async def document_pdf(self, db: AsyncSession, grant: DealGrant, document_id: int) -> tuple[GeneratedDocument, bytes]:
        document = await db.get(GeneratedDocument, document_id)
        if document is None or document.mandate_id != grant.mandate.id:
            raise ResourceNotFoundError("Document not found")
        return document, pdf(document.subject, document.body)

    # The deal page (DEAL-03)

    async def tasks(self, db: AsyncSession, grant: DealGrant, now: datetime) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Task, User.name)
                .join(User, User.id == Task.assignee_id)
                .where(Task.mandate_id == grant.mandate.id)
                .order_by(Task.completed_at.is_not(None), Task.due_date, Task.id)
            )
        ).all()
        return [{**task_read(task, now.date()), "assignee_name": name} for task, name in rows]
