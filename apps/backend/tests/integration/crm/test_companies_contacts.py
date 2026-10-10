from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.interfaces.main import app
from src.modules.audit.models import AuditEntry
from src.modules.company.dependencies import get_annual_accounts, get_enterprise_register
from src.modules.company.ports import FiledAccounts, RegisterEntry, RegisterUnavailableError
from src.modules.picklist.models import PicklistValue
from src.modules.picklist.service import seed_default_picklists
from src.modules.role.permissions import RoleName
from tests.integration.foundation.helpers import login, make_user

pytestmark = pytest.mark.asyncio

VALID = "BE0403.170.701"
VALID_2 = "BE0202.239.951"
INVALID = "BE0403.170.702"
NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


class FakeRegister:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def lookup(self, enterprise_number: str) -> RegisterEntry | None:
        if self.fail:
            raise RegisterUnavailableError("down")
        return RegisterEntry(
            legal_name="Acme Belgium NV", address="Rue de la Loi 1, 1000 Brussels", nace_code="62010", legal_form="NV"
        )


class FakeAccounts:
    async def latest(self, enterprise_number: str, years: int) -> list[FiledAccounts]:
        return [
            FiledAccounts(year, date(year + 1, 6, 30), Decimal(1000 * year % 7 + 1000), Decimal(200), Decimal(50), Decimal(12))
            for year in (2025, 2024, 2023, 2022)
        ][:years]


@pytest.fixture
async def analyst(client: AsyncClient, seeded_db: AsyncSession):
    await seed_default_picklists(seeded_db)
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    headers = await login(client, "ana@firm.be")
    app.dependency_overrides[get_enterprise_register] = FakeRegister
    app.dependency_overrides[get_annual_accounts] = FakeAccounts
    set_clock(FrozenClock(NOW))
    yield headers
    set_clock(SystemClock())


async def country(db: AsyncSession, code: str) -> int:
    return (
        await db.execute(select(PicklistValue.id).where(PicklistValue.kind == "country", PicklistValue.code == code))
    ).scalar_one()


async def create_company(client: AsyncClient, headers, **fields) -> dict:
    response = await client.post("/api/v1/companies/", json=fields, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def belgian(client, headers, db, number=VALID, **fields) -> dict:
    return await create_company(
        client, headers, type="target", country_id=await country(db, "BE"), enterprise_number=number, **fields
    )


# CO-01 c1: a valid enterprise number pre-fills legal name, address, NACE code and legal form.
async def test_valid_enterprise_number_prefills_from_kbo(client, seeded_db, analyst):
    lookup = await client.post("/api/v1/companies/lookup", json={"enterprise_number": VALID}, headers=analyst)
    assert lookup.json() == {
        "enterprise_number": VALID,
        "available": True,
        "name": "Acme Belgium NV",
        "address": "Rue de la Loi 1, 1000 Brussels",
        "nace_code": "62010",
        "legal_form": "NV",
    }

    company = await belgian(client, analyst, seeded_db)
    assert (company["name"], company["nace_code"], company["legal_form"], company["register_source"]) == (
        "Acme Belgium NV",
        "62010",
        "NV",
        "kbo",
    )
    assert company["address"] == "Rue de la Loi 1, 1000 Brussels"


# CO-01 c2: same number or similar name shows the duplicate, with a link to open it.
async def test_duplicates_by_number_or_similar_name_are_shown(client, seeded_db, analyst):
    first = await belgian(client, analyst, seeded_db)
    be = await country(seeded_db, "BE")

    same_number = await client.post(
        "/api/v1/companies/",
        json={"name": "Other", "type": "target", "country_id": be, "enterprise_number": "0403170701"},
        headers=analyst,
    )
    assert same_number.status_code == 409
    detail = same_number.json()["detail"]
    assert detail["can_confirm"] is False
    assert detail["duplicates"][0] | {} == {
        "id": first["id"],
        "name": "Acme Belgium NV",
        "enterprise_number": VALID,
        "reason": "same_number",
        "url": f"/api/v1/companies/{first['id']}",
    }
    assert (await client.get(detail["duplicates"][0]["url"], headers=analyst)).status_code == 200

    fr = await country(seeded_db, "FR")
    similar = {"name": "ACME Belgium", "type": "lender", "country_id": fr}
    response = await client.post("/api/v1/companies/", json=similar, headers=analyst)
    assert response.status_code == 409
    assert response.json()["detail"]["can_confirm"] is True
    assert response.json()["detail"]["duplicates"][0]["reason"] == "similar_name"

    await create_company(client, analyst, **similar, ignore_similar=True)


# CO-01 c3: name, country and type are required; type is one of the six.
async def test_name_country_and_type_are_required(client, seeded_db, analyst):
    fr = await country(seeded_db, "FR")
    for payload in (
        {"type": "target", "country_id": fr},
        {"name": "X", "country_id": fr},
        {"name": "X", "type": "target"},
        {"name": "X", "type": "bank", "country_id": fr},
    ):
        response = await client.post("/api/v1/companies/", json=payload, headers=analyst)
        assert response.status_code == 422, payload
    for company_type in ("target", "strategic_buyer", "financial_investor", "lender", "advisor", "other"):
        await create_company(client, analyst, name=f"Co {company_type}", type=company_type, country_id=fr)


# CO-01 c4: a checksum failure is an inline (field-level) error.
async def test_invalid_enterprise_number_is_an_inline_error(client, seeded_db, analyst):
    response = await client.post(
        "/api/v1/companies/",
        json={"name": "X", "type": "target", "country_id": await country(seeded_db, "BE"), "enterprise_number": INVALID},
        headers=analyst,
    )
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["field"] == "enterprise_number"
    assert "checksum" in error["message"]
    assert INVALID not in response.text


# CO-01 c5: a foreign company has no enterprise number but takes a VAT or registry number.
async def test_foreign_company_takes_vat_or_registry_number(client, seeded_db, analyst):
    fr = await country(seeded_db, "FR")
    company = await create_company(
        client, analyst, name="Paris SAS", type="strategic_buyer", country_id=fr, vat_or_registry_number="FR40303265045"
    )
    assert company["enterprise_number"] is None
    assert company["vat_or_registry_number"] == "FR40303265045"

    missing = await client.post(
        "/api/v1/companies/",
        json={"name": "Gent", "type": "target", "country_id": await country(seeded_db, "BE")},
        headers=analyst,
    )
    assert missing.status_code == 422
    assert missing.json()["errors"][0]["field"] == "enterprise_number"


# CO-01 c6: the register is down, the user continues with manual entry.
async def test_kbo_failure_allows_manual_entry(client, seeded_db, analyst):
    app.dependency_overrides[get_enterprise_register] = lambda: FakeRegister(fail=True)
    lookup = await client.post("/api/v1/companies/lookup", json={"enterprise_number": VALID}, headers=analyst)
    assert lookup.json()["available"] is False

    company = await belgian(client, analyst, seeded_db, name="Manual NV", legal_form="NV", address="Somewhere 1")
    assert (company["name"], company["register_source"], company["address"]) == ("Manual NV", None, "Somewhere 1")


# CO-02 c1: a year with revenue, EBITDA, net debt and FTE in EUR thousands.
async def test_add_a_year_of_financials(client, seeded_db, analyst):
    company = await belgian(client, analyst, seeded_db)
    response = await client.put(
        f"/api/v1/companies/{company['id']}/financials/2025",
        json={"revenue": "12500", "ebitda": "2100.5", "net_debt": "-300", "fte": "85"},
        headers=analyst,
    )
    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]
    assert {k: Decimal(v["value"]) for k, v in metrics.items()} == {
        "revenue": Decimal("12500"),
        "ebitda": Decimal("2100.5"),
        "net_debt": Decimal("-300"),
        "fte": Decimal("85"),
    }


# CO-02 c2: Import loads the latest 3 years with source and date.
async def test_nbb_import_loads_latest_three_years(client, seeded_db, analyst):
    company = await belgian(client, analyst, seeded_db)
    response = await client.post(f"/api/v1/companies/{company['id']}/financials/import", headers=analyst)
    assert response.status_code == 200, response.text
    assert [year["year"] for year in response.json()] == [2025, 2024, 2023]

    revenue = response.json()[0]["metrics"]["revenue"]["imported"]
    assert revenue["source"] == "nbb"
    assert revenue["source_date"] == "2026-06-30"
    assert revenue["recorded_at"].startswith("2026-10-10T09:00")


# CO-02 c3: a manual override keeps the imported value and is labelled with user and date.
async def test_manual_override_keeps_imported_value(client, seeded_db, analyst):
    company = await belgian(client, analyst, seeded_db)
    await client.post(f"/api/v1/companies/{company['id']}/financials/import", headers=analyst)
    user_id = (await client.get("/api/v1/users/me", headers=analyst)).json()["id"]

    await client.put(f"/api/v1/companies/{company['id']}/financials/2025", json={"ebitda": "999"}, headers=analyst)

    year = (await client.get(f"/api/v1/companies/{company['id']}/financials", headers=analyst)).json()[0]
    ebitda = year["metrics"]["ebitda"]
    assert Decimal(ebitda["value"]) == Decimal("999")
    assert Decimal(ebitda["imported"]["value"]) == Decimal("200")
    assert ebitda["override"]["recorded_by"] == user_id
    assert ebitda["override"]["recorded_at"].startswith("2026-10-10")
    assert year["metrics"]["revenue"]["override"] is None


# CO-02 c4: another currency stores the original currency and the EUR rate.
async def test_foreign_currency_keeps_original_and_rate(client, seeded_db, analyst):
    company = await belgian(client, analyst, seeded_db)
    url = f"/api/v1/companies/{company['id']}/financials/2025"
    assert (await client.put(url, json={"revenue": "1000", "currency": "USD"}, headers=analyst)).status_code == 422

    response = await client.put(
        url, json={"revenue": "1000", "fte": "10", "currency": "USD", "eur_rate": "0.92"}, headers=analyst
    )
    revenue = response.json()["metrics"]["revenue"]["override"]
    assert Decimal(revenue["value"]) == Decimal("920")
    assert (revenue["original_currency"], Decimal(revenue["original_value"]), Decimal(revenue["eur_rate"])) == (
        "USD",
        Decimal("1000"),
        Decimal("0.92"),
    )
    assert Decimal(response.json()["metrics"]["fte"]["value"]) == Decimal("10")


# CO-03 c1: the group tree shows on both companies; AUTHZ-05 reads every group entity.
async def test_parent_link_shows_group_tree_on_both(client, seeded_db, analyst):
    fr = await country(seeded_db, "FR")
    parent = await create_company(client, analyst, name="Holdco", type="strategic_buyer", country_id=fr)
    child = await create_company(client, analyst, name="Opco", type="target", country_id=fr)
    grandchild = await create_company(client, analyst, name="Subco", type="target", country_id=fr, parent_id=child["id"])

    response = await client.patch(f"/api/v1/companies/{child['id']}", json={"parent_id": parent["id"]}, headers=analyst)
    assert response.status_code == 200

    expected = {
        "id": parent["id"],
        "name": "Holdco",
        "children": [
            {"id": child["id"], "name": "Opco", "children": [{"id": grandchild["id"], "name": "Subco", "children": []}]}
        ],
    }
    for company in (parent, child, grandchild):
        assert (await client.get(f"/api/v1/companies/{company['id']}", headers=analyst)).json()["group"] == expected
    members = await client.get(f"/api/v1/companies/{grandchild['id']}/group-members", headers=analyst)
    assert members.json() == sorted([parent["id"], child["id"], grandchild["id"]])


# CO-03 c2: a parent that closes a loop is blocked.
async def test_parent_loop_is_blocked(client, seeded_db, analyst):
    fr = await country(seeded_db, "FR")
    a = await create_company(client, analyst, name="Alpha", type="other", country_id=fr)
    b = await create_company(client, analyst, name="Bravo", type="other", country_id=fr, parent_id=a["id"])

    loop = await client.patch(f"/api/v1/companies/{a['id']}", json={"parent_id": b["id"]}, headers=analyst)
    assert loop.status_code == 422
    assert loop.json()["errors"] == [{"field": "parent_id", "message": "This parent would create a loop in the group"}]
    self_parent = await client.patch(f"/api/v1/companies/{a['id']}", json={"parent_id": a["id"]}, headers=analyst)
    assert self_parent.status_code == 422
    assert (await client.get(f"/api/v1/companies/{a['id']}", headers=analyst)).json()["parent_id"] is None


def contact(**fields) -> dict:
    return {"first_name": "Jan", "last_name": "Peeters", "source": "Referral", **fields}


# CON-01 c1: an existing email triggers a duplicate warning.
async def test_duplicate_email_warns(client, seeded_db, analyst):
    company = await belgian(client, analyst, seeded_db)
    first = await client.post(
        "/api/v1/contacts/",
        json=contact(email="jan@acme.be", company_id=company["id"], function="CFO"),
        headers=analyst,
    )
    assert first.status_code == 201
    assert first.json()["warnings"] == []
    assert first.json()["current_role"]["function"] == "CFO"

    second = await client.post("/api/v1/contacts/", json=contact(email="JAN@acme.be"), headers=analyst)
    assert second.status_code == 201
    assert second.json()["warnings"] == ["duplicate_email"]
    assert second.json()["duplicate_contact_ids"] == [first.json()["id"]]


# CON-01 c2: a new employer keeps the old role as history with an end date.
async def test_employer_change_keeps_history(client, seeded_db, analyst):
    fr = await country(seeded_db, "FR")
    old = await create_company(client, analyst, name="Oldco", type="target", country_id=fr)
    new = await create_company(client, analyst, name="Newco", type="target", country_id=fr)
    created = (
        await client.post("/api/v1/contacts/", json=contact(company_id=old["id"], function="CEO"), headers=analyst)
    ).json()

    set_clock(FrozenClock(datetime(2027, 3, 1, tzinfo=UTC)))
    updated = await client.patch(
        f"/api/v1/contacts/{created['id']}", json={"company_id": new["id"], "function": "Chair"}, headers=analyst
    )

    body = updated.json()
    assert body["current_role"] == {"company_id": new["id"], "function": "Chair", "start_date": "2027-03-01", "end_date": None}
    assert body["history"] == [
        {"company_id": old["id"], "function": "CEO", "start_date": "2026-10-10", "end_date": "2027-03-01"}
    ]


# CON-01 c4: invalid email or phone is an inline error; phone is stored in E.164.
async def test_email_and_phone_are_validated_and_phone_is_e164(client, seeded_db, analyst):
    bad_email = await client.post("/api/v1/contacts/", json=contact(email="not-an-email"), headers=analyst)
    assert bad_email.status_code == 422
    assert bad_email.json()["errors"][0]["field"] == "email"

    bad_phone = await client.post("/api/v1/contacts/", json=contact(phone="+32 12"), headers=analyst)
    assert bad_phone.status_code == 422
    assert bad_phone.json()["errors"][0]["field"] == "phone"

    good = await client.post("/api/v1/contacts/", json=contact(phone="0470 12 34 56"), headers=analyst)
    assert good.json()["phone"] == "+32470123456"
    patched = await client.patch(f"/api/v1/contacts/{good.json()['id']}", json={"phone": "+33 1 42 68 53 00"}, headers=analyst)
    assert patched.json()["phone"] == "+33142685300"


async def test_contact_carries_language_salutation_and_do_not_contact(client, seeded_db, analyst):
    response = await client.post(
        "/api/v1/contacts/", json=contact(language="nl", salutation="Dhr.", do_not_contact=True), headers=analyst
    )
    assert {k: response.json()[k] for k in ("language", "salutation", "do_not_contact")} == {
        "language": "nl",
        "salutation": "Dhr.",
        "do_not_contact": True,
    }
    assert (await client.post("/api/v1/contacts/", json=contact(language="de"), headers=analyst)).status_code == 422


# GDPR-01 c1: legal basis (legitimate interest by default, or consent) and source are stored.
async def test_contact_stores_legal_basis_and_source(client, seeded_db, analyst):
    default = await client.post("/api/v1/contacts/", json=contact(), headers=analyst)
    assert (default.json()["legal_basis"], default.json()["source"]) == ("legitimate_interest", "Referral")

    consent = await client.post("/api/v1/contacts/", json=contact(legal_basis="consent", source="Web form"), headers=analyst)
    stored = (await client.get(f"/api/v1/contacts/{consent.json()['id']}", headers=analyst)).json()
    assert (stored["legal_basis"], stored["source"]) == ("consent", "Web form")

    no_source = {"first_name": "A", "last_name": "B"}
    assert (await client.post("/api/v1/contacts/", json=no_source, headers=analyst)).status_code == 422
    assert (await client.post("/api/v1/contacts/", json=contact(legal_basis="contract"), headers=analyst)).status_code == 422


@pytest.fixture
async def admin(client: AsyncClient, seeded_db: AsyncSession):
    await seed_default_picklists(seeded_db)
    await make_user(seeded_db, "root@firm.be", RoleName.ADMIN)
    return await login(client, "root@firm.be")


# ADM-06 c1: an in-use value can be renamed or deactivated, not deleted.
async def test_in_use_picklist_value_cannot_be_deleted(client, seeded_db, admin):
    sector = (
        await client.post("/api/v1/picklists/", json={"kind": "sector", "code": "tech", "label_en": "Tech"}, headers=admin)
    ).json()
    await create_company(
        client, admin, name="Softco", type="target", country_id=await country(seeded_db, "FR"), sector_id=sector["id"]
    )

    deleted = await client.delete(f"/api/v1/picklists/{sector['id']}", headers=admin)
    assert deleted.status_code == 409

    renamed = await client.patch(f"/api/v1/picklists/{sector['id']}", json={"label_en": "Technology"}, headers=admin)
    assert renamed.json()["label_en"] == "Technology"
    deactivated = await client.patch(f"/api/v1/picklists/{sector['id']}", json={"is_active": False}, headers=admin)
    assert deactivated.json()["is_active"] is False
    active = (await client.get("/api/v1/picklists/?kind=sector", headers=admin)).json()
    assert sector["id"] not in [v["id"] for v in active]

    unused = (
        await client.post(
            "/api/v1/picklists/", json={"kind": "deal_type", "code": "sell", "label_en": "Sell-side"}, headers=admin
        )
    ).json()
    assert (await client.delete(f"/api/v1/picklists/{unused['id']}", headers=admin)).status_code == 204
    actions = set((await seeded_db.execute(select(AuditEntry.action))).scalars())
    assert {"picklist.created", "picklist.updated", "picklist.deleted"} <= actions


# ADM-06 c2: a new value shows in EN, FR and NL once translated; EN is required.
async def test_new_value_appears_in_all_three_languages(client, seeded_db, admin):
    no_en = await client.post(
        "/api/v1/picklists/", json={"kind": "deal_stage", "code": "lead", "label_fr": "Piste"}, headers=admin
    )
    assert no_en.status_code == 422

    created = await client.post(
        "/api/v1/picklists/", json={"kind": "deal_stage", "code": "lead", "label_en": "Lead"}, headers=admin
    )
    assert created.json()["translated"] is False
    await client.patch(
        f"/api/v1/picklists/{created.json()['id']}", json={"label_fr": "Piste", "label_nl": "Lead NL"}, headers=admin
    )

    labels = {}
    for lang in ("en", "fr", "nl"):
        values = (await client.get(f"/api/v1/picklists/?kind=deal_stage&lang={lang}", headers=admin)).json()
        labels[lang] = values[0]["label"]
        assert values[0]["translated"] is True
    assert labels == {"en": "Lead", "fr": "Piste", "nl": "Lead NL"}


async def test_only_admins_manage_picklists(client, seeded_db, analyst):
    response = await client.post("/api/v1/picklists/", json={"kind": "sector", "code": "x", "label_en": "X"}, headers=analyst)
    assert response.status_code == 403
    assert (await client.get("/api/v1/picklists/?kind=country", headers=analyst)).status_code == 200


# Lists behind the companies and contacts pages: name search, newest-first is not needed, alphabetical is.
async def test_companies_and_contacts_can_be_listed_and_searched(client, seeded_db, analyst):
    nl = await country(seeded_db, "NL")
    await create_company(client, analyst, name="Zeta Logistics", type="target", country_id=nl, vat_or_registry_number="Z1")
    await create_company(client, analyst, name="Alpha Foods", type="lender", country_id=nl, vat_or_registry_number="A1")

    companies = (await client.get("/api/v1/companies/", headers=analyst)).json()
    assert [company["name"] for company in companies] == ["Alpha Foods", "Zeta Logistics"]
    found = (await client.get("/api/v1/companies/?q=zeta", headers=analyst)).json()
    assert [company["name"] for company in found] == ["Zeta Logistics"]

    await client.post(
        "/api/v1/contacts/", json={"first_name": "Bea", "last_name": "Peeters", "source": "Forum"}, headers=analyst
    )
    await client.post(
        "/api/v1/contacts/", json={"first_name": "Ann", "last_name": "Janssens", "source": "Forum"}, headers=analyst
    )
    contacts = (await client.get("/api/v1/contacts/", headers=analyst)).json()
    assert [(c["first_name"], c["last_name"]) for c in contacts] == [("Ann", "Janssens"), ("Bea", "Peeters")]
    found = (await client.get("/api/v1/contacts/?q=peet", headers=analyst)).json()
    assert [c["last_name"] for c in found] == ["Peeters"]
