import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import CompanyNotFoundError, GroupLoopError, ValidationError
from ..picklist.schemas import PicklistKind
from ..picklist.service import PicklistService
from .enterprise_number import format_enterprise_number
from .models import Company, FinancialFigure
from .ports import AnnualAccountsSource, EnterpriseRegister, RegisterUnavailableError
from .schemas import (
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    DuplicateCompany,
    FigureRead,
    FigureSource,
    FinancialYearEntry,
    FinancialYearRead,
    GroupNode,
    Metric,
    MetricRead,
    RegisterPrefill,
)

BELGIUM = "BE"
IMPORT_YEARS = 3
SIMILAR_NAME_RATIO = 0.85
LEGAL_FORM_SUFFIXES = {"sa", "nv", "srl", "bv", "bvba", "sprl", "sc", "cv", "scrl", "cvba", "ltd", "gmbh", "inc", "llc", "plc"}


class DuplicateCompanyError(Exception):
    def __init__(self, duplicates: list[DuplicateCompany], blocking: bool) -> None:
        super().__init__("Duplicate company")
        self.duplicates = duplicates
        # Same number blocks for good; a similar name can be confirmed with ignore_similar.
        self.blocking = blocking


def normalize_name(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", ascii_name)
    return " ".join(word for word in words if word not in LEGAL_FORM_SUFFIXES)


def to_read(company: Company) -> dict[str, Any]:
    data = CompanyRead.model_validate(company, from_attributes=True).model_dump()
    if company.enterprise_number:
        data["enterprise_number"] = format_enterprise_number(company.enterprise_number)
    return data


def _snapshot(company: Company) -> dict[str, Any]:
    return CompanyRead.model_validate(company, from_attributes=True).model_dump(mode="json")


class CompanyService:
    def __init__(
        self,
        register: EnterpriseRegister,
        accounts: AnnualAccountsSource,
        audit: AuditService | None = None,
        picklists: PicklistService | None = None,
    ) -> None:
        self.register = register
        self.accounts = accounts
        self.audit = audit or AuditService()
        self.picklists = picklists or PicklistService()

    async def get(self, db: AsyncSession, company_id: int) -> Company:
        company = await db.get(Company, company_id)
        if company is None:
            raise CompanyNotFoundError(f"Company {company_id} not found")
        return company

    async def prefill(self, enterprise_number: str) -> dict[str, Any]:
        formatted = format_enterprise_number(enterprise_number)
        try:
            entry = await self.register.lookup(enterprise_number)
        except RegisterUnavailableError:
            entry = None
        if entry is None:
            return RegisterPrefill(enterprise_number=formatted, available=False).model_dump()
        return RegisterPrefill(
            enterprise_number=formatted,
            available=True,
            name=entry.legal_name,
            address=entry.address,
            nace_code=entry.nace_code,
            legal_form=entry.legal_form,
        ).model_dump()

    async def find_duplicates(
        self,
        db: AsyncSession,
        name: str,
        enterprise_number: str | None,
        vat_or_registry_number: str | None,
        exclude_id: int | None = None,
    ) -> tuple[list[DuplicateCompany], bool]:
        by_number: list[Company] = []
        number_conditions = []
        if enterprise_number:
            number_conditions.append(Company.enterprise_number == enterprise_number)
        if vat_or_registry_number:
            number_conditions.append(Company.vat_or_registry_number == vat_or_registry_number)
        if number_conditions:
            by_number = list((await db.execute(select(Company).where(or_(*number_conditions)))).scalars())

        normalized = normalize_name(name)
        first_word = normalized.split(" ", 1)[0] if normalized else ""
        candidates = (await db.execute(select(Company).where(Company.normalized_name.like(f"{first_word[:3]}%")))).scalars()
        by_name = [
            company
            for company in candidates
            if SequenceMatcher(None, normalized, company.normalized_name).ratio() >= SIMILAR_NAME_RATIO
        ]

        found: dict[int, DuplicateCompany] = {}
        for company, reason in [(c, "same_number") for c in by_number] + [(c, "similar_name") for c in by_name]:
            if company.id == exclude_id or company.id in found:
                continue
            found[company.id] = DuplicateCompany(
                id=company.id,
                name=company.name,
                enterprise_number=format_enterprise_number(company.enterprise_number) if company.enterprise_number else None,
                reason=reason,
                url=f"/api/v1/companies/{company.id}",
            )
        duplicates = list(found.values())
        return duplicates, any(d.reason == "same_number" for d in duplicates)

    async def create(self, db: AsyncSession, values: CompanyCreate, context: AuditContext) -> dict[str, Any]:
        country = await self.picklists.require_active(db, values.country_id, PicklistKind.COUNTRY)
        if values.sector_id is not None:
            await self.picklists.require_active(db, values.sector_id, PicklistKind.SECTOR)
        fields = values.model_dump(exclude={"ignore_similar"})
        register_source = None

        if country.code == BELGIUM:
            if not values.enterprise_number:
                raise ValidationError("enterprise_number is required for a Belgian company", field="enterprise_number")
            fields["vat_or_registry_number"] = None
            prefill = await self.prefill(values.enterprise_number)
            if prefill["available"]:
                register_source = "kbo"
                for key in ("name", "address", "nace_code", "legal_form"):
                    fields[key] = fields[key] or prefill[key]
        elif values.enterprise_number:
            raise ValidationError(
                "enterprise_number applies to Belgian companies; use vat_or_registry_number", field="enterprise_number"
            )

        if not fields["name"]:
            raise ValidationError("name is required", field="name")

        duplicates, blocking = await self.find_duplicates(
            db, fields["name"], fields["enterprise_number"], fields["vat_or_registry_number"]
        )
        if duplicates and (blocking or not values.ignore_similar):
            raise DuplicateCompanyError(duplicates, blocking)

        if fields["parent_id"] is not None:
            await self.get(db, fields["parent_id"])

        company = Company(**fields, normalized_name=normalize_name(fields["name"]), register_source=register_source)
        db.add(company)
        await db.flush()
        self.audit.record(
            db, context, "company.created", record_type="company", record_id=company.id, new_values=_snapshot(company)
        )
        await db.commit()
        return to_read(company)

    async def update(self, db: AsyncSession, company_id: int, values: CompanyUpdate, context: AuditContext) -> dict[str, Any]:
        company = await self.get(db, company_id)
        changes = values.model_dump(exclude_unset=True)
        if "parent_id" in changes and changes["parent_id"] is not None:
            await self.check_parent(db, company.id, changes["parent_id"])
        if changes.get("sector_id") is not None:
            await self.picklists.require_active(db, changes["sector_id"], PicklistKind.SECTOR)
        if "name" in changes and changes["name"] is None or "type" in changes and changes["type"] is None:
            raise ValidationError("name and type cannot be cleared")
        old = _snapshot(company)
        for key, value in changes.items():
            setattr(company, key, value)
        if "name" in changes:
            company.normalized_name = normalize_name(company.name)
        self.audit.record(
            db,
            context,
            "company.updated",
            record_type="company",
            record_id=company.id,
            old_values=old,
            new_values=_snapshot(company),
        )
        await db.commit()
        return to_read(company)

    async def check_parent(self, db: AsyncSession, company_id: int, parent_id: int) -> None:
        if parent_id == company_id:
            raise GroupLoopError("A company cannot be its own parent", field="parent_id")
        current: int | None = (await self.get(db, parent_id)).id
        seen: set[int] = set()
        while current is not None and current not in seen:
            if current == company_id:
                raise GroupLoopError("This parent would create a loop in the group", field="parent_id")
            seen.add(current)
            current = (await db.execute(select(Company.parent_id).where(Company.id == current))).scalar_one_or_none()

    async def _root(self, db: AsyncSession, company: Company) -> Company:
        root, seen = company, {company.id}
        while root.parent_id is not None and root.parent_id not in seen:
            root = await self.get(db, root.parent_id)
            seen.add(root.id)
        return root

    async def group_tree(self, db: AsyncSession, company_id: int) -> GroupNode:
        root = await self._root(db, await self.get(db, company_id))
        node = GroupNode(id=root.id, name=root.name)
        frontier, seen = [node], {root.id}
        while frontier:
            parents = {n.id: n for n in frontier}
            children = (
                await db.execute(select(Company).where(Company.parent_id.in_(parents)).order_by(Company.name))
            ).scalars()
            frontier = []
            for child in children:
                if child.id in seen:
                    continue
                seen.add(child.id)
                child_node = GroupNode(id=child.id, name=child.name)
                parents[child.parent_id].children.append(child_node)  # type: ignore[index]
                frontier.append(child_node)
        return node

    async def group_member_ids(self, db: AsyncSession, company_id: int) -> set[int]:
        """Every company in the same group, for conflict checks (AUTHZ-05) and buyer lists."""
        ids: set[int] = set()
        stack = [await self.group_tree(db, company_id)]
        while stack:
            node = stack.pop()
            ids.add(node.id)
            stack.extend(node.children)
        return ids

    async def detail(self, db: AsyncSession, company_id: int) -> dict[str, Any]:
        company = await self.get(db, company_id)
        return {**to_read(company), "group": (await self.group_tree(db, company_id)).model_dump()}

    async def set_financial_year(
        self, db: AsyncSession, company_id: int, year: int, entry: FinancialYearEntry, context: AuditContext
    ) -> dict[str, Any]:
        await self.get(db, company_id)
        now = context.clock.now()
        rate = Decimal(1) if entry.currency == "EUR" else entry.eur_rate
        assert rate is not None
        for metric in Metric:
            original = getattr(entry, metric.value)
            if original is None:
                continue
            is_money = metric != Metric.FTE
            value = (original * rate).quantize(Decimal("0.01")) if is_money else original
            await self._upsert(
                db,
                company_id,
                year,
                metric,
                FigureSource.MANUAL,
                value=value,
                recorded_at=now,
                recorded_by=context.user_id,
                source_date=None,
                original_currency=entry.currency if is_money else "EUR",
                original_value=original if is_money and entry.currency != "EUR" else None,
                eur_rate=rate if is_money and entry.currency != "EUR" else None,
            )
        self.audit.record(
            db,
            context,
            "company.financials_set",
            record_type="company",
            record_id=company_id,
            new_values={"year": year, **entry.model_dump(mode="json")},
        )
        await db.commit()
        return await self._year(db, company_id, year)

    async def import_financials(self, db: AsyncSession, company_id: int, context: AuditContext) -> list[dict[str, Any]]:
        company = await self.get(db, company_id)
        if not company.enterprise_number:
            raise ValidationError("Only a company with a Belgian enterprise number has NBB filed accounts")
        try:
            filings = await self.accounts.latest(company.enterprise_number, IMPORT_YEARS)
        except RegisterUnavailableError as error:
            raise ValidationError("The NBB is unavailable: enter the figures manually") from error
        filings = sorted(filings, key=lambda f: f.year, reverse=True)[:IMPORT_YEARS]
        now = context.clock.now()
        for filing in filings:
            for metric in Metric:
                value = getattr(filing, metric.value)
                if value is None:
                    continue
                await self._upsert(
                    db,
                    company_id,
                    filing.year,
                    metric,
                    FigureSource.NBB,
                    value=value,
                    recorded_at=now,
                    recorded_by=context.user_id,
                    source_date=filing.filed_on,
                    original_currency="EUR",
                    original_value=None,
                    eur_rate=None,
                )
        self.audit.record(
            db,
            context,
            "company.financials_imported",
            record_type="company",
            record_id=company_id,
            new_values={"years": [f.year for f in filings]},
        )
        await db.commit()
        return [await self._year(db, company_id, f.year) for f in filings]

    async def _upsert(
        self, db: AsyncSession, company_id: int, year: int, metric: Metric, source: FigureSource, **fields: Any
    ) -> None:
        existing = (
            await db.execute(
                select(FinancialFigure).where(
                    FinancialFigure.company_id == company_id,
                    FinancialFigure.year == year,
                    FinancialFigure.metric == metric.value,
                    FinancialFigure.source == source.value,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(FinancialFigure(company_id=company_id, year=year, metric=metric.value, source=source.value, **fields))
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
        await db.flush()

    async def financials(self, db: AsyncSession, company_id: int) -> list[dict[str, Any]]:
        await self.get(db, company_id)
        years = (
            await db.execute(
                select(FinancialFigure.year)
                .where(FinancialFigure.company_id == company_id)
                .distinct()
                .order_by(FinancialFigure.year.desc())
            )
        ).scalars()
        return [await self._year(db, company_id, year) for year in list(years)]

    async def _year(self, db: AsyncSession, company_id: int, year: int) -> dict[str, Any]:
        figures = (
            await db.execute(
                select(FinancialFigure).where(FinancialFigure.company_id == company_id, FinancialFigure.year == year)
            )
        ).scalars()
        by_metric: dict[Metric, dict[str, FigureRead]] = {}
        for figure in figures:
            by_metric.setdefault(Metric(figure.metric), {})[figure.source] = FigureRead.model_validate(
                figure, from_attributes=True
            )
        metrics = {}
        for metric, sources in by_metric.items():
            imported, override = sources.get(FigureSource.NBB.value), sources.get(FigureSource.MANUAL.value)
            chosen = override or imported
            assert chosen is not None
            metrics[metric] = MetricRead(value=chosen.value, imported=imported, override=override)
        return FinancialYearRead(year=year, metrics=metrics).model_dump(mode="json")
