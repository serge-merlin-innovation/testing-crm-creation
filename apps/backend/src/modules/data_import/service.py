"""Excel import of contacts and companies (CON-05): upload, map columns, preview, confirm.

Above `BACKGROUND_THRESHOLD` rows the confirmed import runs as a scheduled job and the uploader is
notified when it finishes.
"""

import io
import re
from datetime import datetime
from typing import Any

from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]
from pydantic import EmailStr, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.clock import FrozenClock
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import ImportNotFoundError, ValidationError
from ..company.enterprise_number import normalize_enterprise_number
from ..company.models import Company
from ..company.schemas import CompanyType
from ..company.service import BELGIUM, normalize_name
from ..contact.models import Contact, Employment
from ..contact.schemas import ContactLanguage, to_e164
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..picklist.models import PicklistValue
from ..picklist.schemas import PicklistKind
from ..user.models import User
from .models import DataImport
from .schemas import REQUIRED_FIELDS, TARGET_FIELDS, ImportEntity, ImportStatus, RowStatus

BACKGROUND_THRESHOLD = 50_000
PREVIEW_ROWS = 200
MAX_ROWS = 500_000
DEFAULT_SOURCE = "Excel import"
EMAIL = TypeAdapter(EmailStr)


def _cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def read_workbook(content: bytes) -> tuple[list[str], list[list[Any]]]:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as error:
        raise ValidationError("The file is not a readable Excel workbook (.xlsx)", field="file") from error
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if header is None:
        raise ValidationError("The sheet is empty", field="file")
    headers = [str(value).strip() if value is not None else f"Column {index + 1}" for index, value in enumerate(header)]
    data: list[list[Any]] = []
    for row in rows:
        values = [_cell(value) for value in row[: len(headers)]]
        if any(value is not None for value in values):
            data.append(values + [None] * (len(headers) - len(values)))
        if len(data) > MAX_ROWS:
            raise ValidationError(f"At most {MAX_ROWS} rows per file", field="file")
    workbook.close()
    return headers, data


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def suggest_mapping(entity: ImportEntity, headers: list[str]) -> dict[str, str]:
    by_key = {_key(header): header for header in headers}
    return {field: by_key[_key(field)] for field in TARGET_FIELDS[entity] if _key(field) in by_key}


class Validator:
    """Checks rows against the database and against earlier rows of the same file."""

    def __init__(self, entity: ImportEntity) -> None:
        self.entity = entity
        self.seen: dict[str, int] = {}
        self.existing: dict[str, int] = {}
        self.companies: dict[str, int] = {}
        self.countries: dict[str, int] = {}

    async def load(self, db: AsyncSession) -> None:
        if self.entity == ImportEntity.CONTACT:
            rows = await db.execute(select(func.lower(Contact.email), Contact.id).where(Contact.email.is_not(None)))
            self.existing = {f"email:{email}": cid for email, cid in rows.tuples()}
            self.companies = {
                name: cid for name, cid in (await db.execute(select(Company.normalized_name, Company.id))).tuples()
            }
        else:
            for company in (await db.execute(select(Company))).scalars():
                self.existing[f"name:{company.normalized_name}"] = company.id
                if company.enterprise_number:
                    self.existing[f"number:{company.enterprise_number}"] = company.id
                if company.vat_or_registry_number:
                    self.existing[f"number:{company.vat_or_registry_number.lower()}"] = company.id
            countries = await db.execute(
                select(PicklistValue.code, PicklistValue.id).where(
                    PicklistValue.kind == PicklistKind.COUNTRY.value, PicklistValue.is_active.is_(True)
                )
            )
            self.countries = {code.upper(): cid for code, cid in countries.tuples()}

    def check(self, number: int, values: dict[str, Any]) -> dict[str, Any]:
        errors = [f"{field} is required" for field in REQUIRED_FIELDS[self.entity] if not values.get(field)]
        clean = dict(values)
        keys: list[str] = []
        if self.entity == ImportEntity.CONTACT:
            keys = self._contact(clean, errors)
        else:
            keys = self._company(clean, errors)
        result: dict[str, Any] = {"row": number, "values": values, "errors": errors, "duplicate_of": None}
        if errors:
            result["status"] = RowStatus.ERROR.value
            return result
        for key in keys:
            if key in self.existing:
                result.update(status=RowStatus.DUPLICATE.value, duplicate_of=self.existing[key])
                return result
            if key in self.seen:
                result.update(status=RowStatus.DUPLICATE.value, errors=[f"Same as row {self.seen[key]}"])
                return result
        for key in keys:
            self.seen[key] = number
        result.update(status=RowStatus.NEW.value, clean=clean)
        return result

    def _contact(self, clean: dict[str, Any], errors: list[str]) -> list[str]:
        for name in ("first_name", "last_name"):
            if clean.get(name) and len(clean[name]) > 100:
                errors.append(f"{name} is longer than 100 characters")
        if clean.get("email"):
            try:
                clean["email"] = str(EMAIL.validate_python(clean["email"]))
            except PydanticValidationError:
                errors.append("email is not a valid address")
        if clean.get("phone"):
            try:
                clean["phone"] = to_e164(clean["phone"])
            except ValueError:
                errors.append("phone is not a valid number")
        language = (clean.get("language") or ContactLanguage.EN.value).lower()
        if language not in {value.value for value in ContactLanguage}:
            errors.append("language must be en, fr or nl")
        clean["language"] = language
        if clean.get("company"):
            company_id = self.companies.get(normalize_name(clean["company"]))
            if company_id is None:
                errors.append(f"company '{clean['company']}' does not exist")
            clean["company_id"] = company_id
        return [f"email:{clean['email'].lower()}"] if clean.get("email") and not errors else []

    def _company(self, clean: dict[str, Any], errors: list[str]) -> list[str]:
        company_type = (clean.get("type") or "").strip().lower().replace(" ", "_").replace("-", "_")
        if clean.get("type") and company_type not in {value.value for value in CompanyType}:
            errors.append("type must be one of " + ", ".join(value.value for value in CompanyType))
        clean["type"] = company_type
        country = (clean.get("country") or "").upper()
        if clean.get("country") and country not in self.countries:
            errors.append(f"country '{clean['country']}' is not a known country code")
        clean["country_id"] = self.countries.get(country)
        keys: list[str] = []
        if clean.get("enterprise_number"):
            digits = normalize_enterprise_number(clean["enterprise_number"])
            if digits is None:
                errors.append("enterprise_number checksum does not match")
            clean["enterprise_number"] = digits
            keys.append(f"number:{digits}")
        elif country == BELGIUM:
            errors.append("enterprise_number is required for a Belgian company")
        if country == BELGIUM:
            clean["vat_or_registry_number"] = None
        elif clean.get("vat_or_registry_number"):
            keys.append(f"number:{clean['vat_or_registry_number'].lower()}")
        if clean.get("name"):
            if len(clean["name"]) > 200:
                errors.append("name is longer than 200 characters")
            keys.append(f"name:{normalize_name(clean['name'])}")
        return keys


class ImportService:
    def __init__(self, notifications: NotificationService, audit: AuditService | None = None) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()

    async def get(self, db: AsyncSession, import_id: int) -> DataImport:
        record = await db.get(DataImport, import_id)
        if record is None:
            raise ImportNotFoundError(f"Import {import_id} not found")
        return record

    async def upload(
        self, db: AsyncSession, user: dict[str, Any], entity: ImportEntity, filename: str, content: bytes, now: datetime
    ) -> dict[str, Any]:
        headers, rows = read_workbook(content)
        record = DataImport(
            entity=entity.value,
            filename=filename[:255],
            uploaded_by=user["id"],
            uploaded_at=now,
            headers=headers,
            rows=rows,
            status=ImportStatus.UPLOADED.value,
        )
        db.add(record)
        await db.commit()
        return self.upload_read(record)

    def upload_read(self, record: DataImport) -> dict[str, Any]:
        entity = ImportEntity(record.entity)
        return {
            "id": record.id,
            "entity": entity,
            "filename": record.filename,
            "status": record.status,
            "headers": record.headers,
            "row_count": len(record.rows),
            "fields": list(TARGET_FIELDS[entity]),
            "required_fields": list(REQUIRED_FIELDS[entity]),
            "suggested_mapping": suggest_mapping(entity, record.headers),
            "uploaded_at": record.uploaded_at,
        }

    def _map(self, record: DataImport, mapping: dict[str, str]) -> list[dict[str, Any]]:
        entity = ImportEntity(record.entity)
        unknown = sorted(set(mapping) - set(TARGET_FIELDS[entity]))
        if unknown:
            raise ValidationError(f"Unknown fields: {', '.join(unknown)}", field="mapping")
        missing_columns = sorted(column for column in mapping.values() if column not in record.headers)
        if missing_columns:
            raise ValidationError(f"Columns not in the file: {', '.join(missing_columns)}", field="mapping")
        unmapped = [field for field in REQUIRED_FIELDS[entity] if field not in mapping]
        if unmapped:
            raise ValidationError(f"Map a column to: {', '.join(unmapped)}", field="mapping")
        index = {field: record.headers.index(column) for field, column in mapping.items()}
        return [{field: row[position] for field, position in index.items()} for row in record.rows]

    async def _validate(self, db: AsyncSession, record: DataImport, mapping: dict[str, str]) -> list[dict[str, Any]]:
        validator = Validator(ImportEntity(record.entity))
        await validator.load(db)
        # Spreadsheet row numbers: the header is row 1.
        return [validator.check(number, values) for number, values in enumerate(self._map(record, mapping), start=2)]

    @staticmethod
    def _counts(results: list[dict[str, Any]]) -> dict[str, int]:
        counts = {status.value: 0 for status in RowStatus}
        for result in results:
            counts[result["status"]] += 1
        return counts

    @staticmethod
    def _public(result: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in result.items() if key != "clean"}

    async def preview(self, db: AsyncSession, import_id: int, mapping: dict[str, str]) -> dict[str, Any]:
        record = await self.get(db, import_id)
        if record.status != ImportStatus.UPLOADED.value:
            raise ValidationError("This import was already confirmed", field="mapping")
        results = await self._validate(db, record, mapping)
        record.mapping = mapping
        await db.commit()
        # Errors and duplicates first: they are what the admin must look at before confirming.
        order = {RowStatus.ERROR.value: 0, RowStatus.DUPLICATE.value: 1, RowStatus.NEW.value: 2}
        shown = sorted(results, key=lambda result: (order[result["status"]], result["row"]))[:PREVIEW_ROWS]
        return {
            "id": record.id,
            "status": record.status,
            "counts": self._counts(results),
            "rows": [self._public(result) for result in shown],
        }

    async def confirm(self, db: AsyncSession, import_id: int, context: AuditContext) -> dict[str, Any]:
        record = await self.get(db, import_id)
        if record.status != ImportStatus.UPLOADED.value:
            raise ValidationError("This import was already confirmed", field="mapping")
        if record.mapping is None:
            raise ValidationError("Preview the import before confirming", field="mapping")
        if len(record.rows) > BACKGROUND_THRESHOLD:
            record.status = ImportStatus.QUEUED.value
            self.audit.record(db, context, "data_import.queued", record_type="data_import", record_id=record.id)
            await db.commit()
            return self.read(record)
        await self.run(db, record, context.clock.now(), context)
        await db.commit()
        return self.read(record)

    async def run(self, db: AsyncSession, record: DataImport, now: datetime, context: AuditContext | None) -> None:
        assert record.mapping is not None
        results = await self._validate(db, record, record.mapping)
        created = await self._create(
            db, ImportEntity(record.entity), [r for r in results if r["status"] == RowStatus.NEW.value], record.uploaded_by
        )
        background = record.status == ImportStatus.QUEUED.value
        record.results = [self._public(result) for result in results]
        record.status = ImportStatus.COMPLETED.value
        record.completed_at = now
        counts = self._counts(results)
        summary = {"created": created, **counts}
        if context is not None:
            self.audit.record(
                db, context, "data_import.completed", record_type="data_import", record_id=record.id, new_values=summary
            )
        else:
            self.audit.record(
                db,
                AuditContext(user_id=record.uploaded_by, ip_address=None, user_agent=None, clock=FrozenClock(now)),
                "data_import.completed",
                record_type="data_import",
                record_id=record.id,
                new_values=summary,
            )
        if background:
            uploader = await db.get(User, record.uploaded_by)
            if uploader is not None:
                await self.notifications.add(
                    db,
                    Message(
                        user_id=uploader.id,
                        email=uploader.email,
                        kind=EventKind.IMPORT_COMPLETED.value,
                        title=f"Import of {record.filename} finished",
                        body=(
                            f"{created} {record.entity}s created, {counts['duplicate']} duplicates skipped, "
                            f"{counts['error']} rows with errors."
                        ),
                        link=f"/imports?id={record.id}",
                    ),
                    now,
                )

    async def _create(self, db: AsyncSession, entity: ImportEntity, rows: list[dict[str, Any]], owner_id: int) -> int:
        if entity == ImportEntity.COMPANY:
            for row in rows:
                clean = row["clean"]
                db.add(
                    Company(
                        name=clean["name"],
                        normalized_name=normalize_name(clean["name"]),
                        type=clean["type"],
                        country_id=clean["country_id"],
                        enterprise_number=clean.get("enterprise_number"),
                        vat_or_registry_number=clean.get("vat_or_registry_number"),
                        legal_form=clean.get("legal_form"),
                        nace_code=clean.get("nace_code"),
                        address=clean.get("address"),
                    )
                )
            await db.flush()
            return len(rows)
        contacts: list[tuple[Contact, dict[str, Any]]] = []
        for row in rows:
            clean = row["clean"]
            contact = Contact(
                first_name=clean["first_name"],
                last_name=clean["last_name"],
                email=clean.get("email"),
                phone=clean.get("phone"),
                language=clean["language"],
                salutation=clean.get("salutation"),
                source=clean.get("source") or DEFAULT_SOURCE,
                owner_id=owner_id,
            )
            db.add(contact)
            contacts.append((contact, clean))
        await db.flush()
        for contact, clean in contacts:
            if clean.get("company_id"):
                db.add(Employment(contact_id=contact.id, company_id=clean["company_id"], function=clean.get("function")))
        await db.flush()
        return len(rows)

    async def run_queued(self, db: AsyncSession, now: datetime) -> None:
        queued = (
            await db.execute(select(DataImport).where(DataImport.status == ImportStatus.QUEUED.value).order_by(DataImport.id))
        ).scalars()
        for record in list(queued):
            await self.run(db, record, now, None)
            await db.commit()
            await self.notifications.flush_emails()

    def read(self, record: DataImport) -> dict[str, Any]:
        counts = self._counts(record.results) if record.results is not None else None
        return {
            "id": record.id,
            "entity": record.entity,
            "filename": record.filename,
            "status": record.status,
            "row_count": len(record.rows),
            "background": len(record.rows) > BACKGROUND_THRESHOLD,
            "counts": counts,
            "created": counts[RowStatus.NEW.value] if counts else 0,
            "error_file_url": f"/api/v1/imports/{record.id}/errors.xlsx" if counts and counts[RowStatus.ERROR.value] else None,
            "completed_at": record.completed_at,
        }

    async def error_file(self, db: AsyncSession, import_id: int) -> bytes:
        record = await self.get(db, import_id)
        if record.results is None:
            raise ValidationError("The import has not finished", field="import_id")
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("Errors")
        sheet.append(["Row", *record.headers, "Errors"])
        for result in record.results:
            if result["status"] == RowStatus.ERROR.value:
                sheet.append([result["row"], *record.rows[result["row"] - 2], "; ".join(result["errors"])])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()
