from typing import Annotated, Any

from fastapi import APIRouter, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..common.downloads import attachment_header
from ..mandate.policy import EditGrant, ExportGrant, ReadGrant
from ..role.authorization import require_permission
from ..role.permissions import Permission
from ..task.schemas import DealTaskRead
from .dependencies import OfferServiceDep, ProcessServiceDep, TemplateServiceDep
from .schemas import (
    BidDeadlines,
    Funnel,
    GeneratedRead,
    LetterRequest,
    LetterResult,
    OfferComparison,
    OfferCreate,
    OfferRead,
    ReportRequest,
    TemplateRead,
    TemplateWrite,
)

router = APIRouter(tags=["Bidding process"])
templates_router = APIRouter(tags=["Templates"])

HIDDEN: dict[int | str, dict[str, Any]] = {404: {"description": "Not found, or not visible to you"}}
PDF = "application/pdf"
TemplateManagerDep = Annotated[dict[str, Any], require_permission(Permission.SETTINGS_MANAGE)]


def _pdf(content: bytes, filename: str) -> Response:
    return Response(content, media_type=PDF, headers={"Content-Disposition": attachment_header(filename)})


@router.get(
    "/{mandate_id}/offers",
    response_model=OfferComparison,
    summary="Bid comparison: latest offer per buyer and round by EV, with implied EV/EBITDA, plus every version",
    description="Offer values are not fee fields: every deal member reads them, analysts included.",
    responses=HIDDEN,
)
async def get_offers(grant: ReadGrant, db: AsyncSessionDep, service: OfferServiceDep) -> dict[str, Any]:
    return await service.comparison(db, grant)


@router.post(
    "/{mandate_id}/offers",
    status_code=201,
    response_model=OfferRead,
    summary="Record an offer, or a revised version of one",
    description="EV and equity value in EUR millions. An offer received after the round's bid deadline is flagged late.",
    responses=HIDDEN,
)
async def add_offer(
    values: OfferCreate, grant: EditGrant, db: AsyncSessionDep, service: OfferServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.add(db, grant, values, context)


@router.put("/{mandate_id}/bid-deadlines", response_model=BidDeadlines, summary="Set the bid deadlines", responses=HIDDEN)
async def put_deadlines(
    values: BidDeadlines, grant: EditGrant, db: AsyncSessionDep, service: OfferServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.set_deadlines(db, grant, values, context)


@router.get("/{mandate_id}/funnel", response_model=Funnel, summary="Counts and conversion per process step", responses=HIDDEN)
async def get_funnel(grant: ReadGrant, db: AsyncSessionDep, service: ProcessServiceDep) -> dict[str, Any]:
    return await service.funnel(db, grant)


@router.get(
    "/{mandate_id}/funnel.pdf",
    summary="The funnel as PDF (audited export)",
    responses={**HIDDEN, 200: {"content": {PDF: {}}}},
)
async def get_funnel_pdf(
    grant: ExportGrant, db: AsyncSessionDep, service: ProcessServiceDep, context: AuditContextDep
) -> Response:
    return _pdf(await service.funnel_pdf(db, grant, context), f"{grant.mandate.code_name}-funnel.pdf")


@router.post(
    "/{mandate_id}/letters",
    response_model=LetterResult,
    summary="Send a process letter to the selected buyers",
    description="Each buyer's contact gets the template in their language with their salutation. Buyers that cannot "
    "receive it come back in `excluded` with the reason (no signed NDA when the letter references the IM, opted out, "
    "Do not contact, ...). Each send is logged as an activity.",
    responses=HIDDEN,
)
async def send_letters(
    values: LetterRequest, grant: EditGrant, db: AsyncSessionDep, service: ProcessServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.send_letters(db, grant, values, context)


@router.post(
    "/{mandate_id}/status-report",
    summary="Generate the client status report (PDF)",
    description="Funnel, timeline vs plan and next steps, in the client's language. No notes, buyer names, offers or "
    "fees. Logged as an activity.",
    responses={**HIDDEN, 200: {"content": {PDF: {}}}},
)
async def status_report(
    grant: ExportGrant,
    db: AsyncSessionDep,
    service: ProcessServiceDep,
    context: AuditContextDep,
    values: ReportRequest | None = None,
) -> Response:
    document, content = await service.status_report(db, grant, (values or ReportRequest()).template_name, context)
    return _pdf(content, f"{grant.mandate.code_name}-status-{document.created_at.date().isoformat()}.pdf")


@router.get(
    "/{mandate_id}/documents",
    response_model=list[GeneratedRead],
    summary="Letters and reports generated on the deal, as they were produced",
    responses=HIDDEN,
)
async def list_documents(grant: ReadGrant, db: AsyncSessionDep, service: ProcessServiceDep) -> list[Any]:
    return list(await service.documents(db, grant))


@router.get(
    "/{mandate_id}/documents/{document_id}",
    summary="A generated letter or report as PDF",
    responses={**HIDDEN, 200: {"content": {PDF: {}}}},
)
async def document_pdf(document_id: int, grant: ExportGrant, db: AsyncSessionDep, service: ProcessServiceDep) -> Response:
    document, content = await service.document_pdf(db, grant, document_id)
    return _pdf(content, f"{grant.mandate.code_name}-{document.kind}-{document.id}.pdf")


@router.get("/{mandate_id}/tasks", response_model=list[DealTaskRead], summary="The deal's tasks, open first", responses=HIDDEN)
async def deal_tasks(
    grant: ReadGrant, db: AsyncSessionDep, service: ProcessServiceDep, clock: ClockDep
) -> list[dict[str, Any]]:
    return await service.tasks(db, grant, clock.now())


@templates_router.get("/", response_model=list[TemplateRead], summary="Letter and report templates")
async def list_templates(db: AsyncSessionDep, service: TemplateServiceDep, _: TemplateManagerDep) -> list[dict[str, Any]]:
    return await service.list(db)


@templates_router.get("/names", summary="Template names and their languages, for picking one on a deal")
async def template_names(db: AsyncSessionDep, service: TemplateServiceDep, _: CurrentUserDep) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in await service.list(db):
        item = grouped.setdefault((row["kind"], row["name"]), {"kind": row["kind"], "name": row["name"], "languages": []})
        item["languages"].append(row["language"])
    return list(grouped.values())


@templates_router.post("/", status_code=201, response_model=TemplateRead, summary="Create a template in one language")
async def create_template(
    values: TemplateWrite, db: AsyncSessionDep, service: TemplateServiceDep, _: TemplateManagerDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.create(db, values, context)


@templates_router.put(
    "/{template_id}",
    response_model=TemplateRead,
    summary="Edit a template",
    description="Audited. Letters and reports generated earlier keep their text.",
)
async def update_template(
    template_id: int,
    values: TemplateWrite,
    db: AsyncSessionDep,
    service: TemplateServiceDep,
    _: TemplateManagerDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.update(db, template_id, values, context)
