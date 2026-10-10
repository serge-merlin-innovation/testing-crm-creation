from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Response, UploadFile

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import ImportServiceDep
from .schemas import ImportEntity, ImportRead, MappingRequest, PreviewRead, UploadRead

router = APIRouter(tags=["Import"])

IMPORT_PERMISSION = Permission.SETTINGS_MANAGE
ImporterDep = Annotated[dict[str, Any], require_permission(IMPORT_PERMISSION)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post(
    "/",
    status_code=201,
    response_model=UploadRead,
    summary="Admin: upload an Excel file of contacts or companies",
    description="Returns the file's columns, the fields to map them to, and a suggested mapping.",
)
async def upload_import(
    db: AsyncSessionDep,
    service: ImportServiceDep,
    user: ImporterDep,
    clock: ClockDep,
    entity: Annotated[ImportEntity, Form()],
    file: Annotated[UploadFile, File(description="An .xlsx workbook; the first sheet's first row is the header")],
) -> dict[str, Any]:
    return await service.upload(db, user, entity, file.filename or "import.xlsx", await file.read(), clock.now())


@router.post(
    "/{import_id}/preview",
    response_model=PreviewRead,
    summary="Admin: map columns and preview new, duplicate and error rows",
    description="Nothing is written until the import is confirmed. Shows up to 200 rows, errors and duplicates first.",
)
async def preview_import(
    import_id: int, values: MappingRequest, db: AsyncSessionDep, service: ImportServiceDep, _: ImporterDep
) -> dict[str, Any]:
    return await service.preview(db, import_id, values.mapping)


@router.post(
    "/{import_id}/confirm",
    response_model=ImportRead,
    summary="Admin: run the previewed import",
    description="Up to 50,000 rows run now. Larger files are queued, run in the background, and notify the uploader.",
)
async def confirm_import(
    import_id: int, db: AsyncSessionDep, service: ImportServiceDep, _: ImporterDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.confirm(db, import_id, context)


@router.get("/{import_id}", response_model=ImportRead, summary="Admin: an import's status and counts")
async def get_import(import_id: int, db: AsyncSessionDep, service: ImportServiceDep, _: ImporterDep) -> dict[str, Any]:
    return service.read(await service.get(db, import_id))


@router.get(
    "/{import_id}/errors.xlsx",
    summary="Admin: download the rows that failed, with the reason per row",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}}},
)
async def download_import_errors(import_id: int, db: AsyncSessionDep, service: ImportServiceDep, _: ImporterDep) -> Response:
    return Response(
        content=await service.error_file(db, import_id),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="import-{import_id}-errors.xlsx"'},
    )
