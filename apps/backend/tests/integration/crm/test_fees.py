"""Ticket #10: fees (DEAL-05), fee-field visibility (AUTHZ-06), invoices (REP-07), ROLE-01 c4 + c5."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.modules.audit.models import AuditEntry
from src.modules.fee.schemas import FeeTermsValues
from src.modules.fee.service import expected_success_fee
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
FEE_KEYS = ("retainer", "success_fee", "expected_fee", "final_fee", "minimum_fee", "lehman")


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.director = await built.actor("dirk", RoleName.DIRECTOR)
    built.outsider = await built.actor("otto", RoleName.PARTNER)
    built.compliance = await built.actor("cora", RoleName.COMPLIANCE)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.client_id = await built.company("Acme Holding")
    yield built
    await built.close()
    set_clock(SystemClock())


async def staff(world, mandate_id: int, actor, role: str) -> None:
    response = await world.partner.client.post(
        f"/api/v1/mandates/{mandate_id}/team", json={"user_id": actor.id, "role": role}, headers=world.partner.headers
    )
    assert response.status_code == 201, response.text


async def deal(world, ev: str = "25000") -> int:
    mandate = await create_mandate(world, world.partner, world.client_id, estimated_ev=ev)
    await staff(world, mandate["id"], world.analyst, "analyst")
    await staff(world, mandate["id"], world.director, "director")
    return mandate["id"]


async def put_fees(actor, mandate_id: int, **body):
    terms = {
        "retainer_monthly": "10000",
        "success_fee_kind": "percent",
        "success_fee_percent": "2",
        "minimum_fee": "0",
        "retainers_creditable": False,
        **body,
    }
    return await actor.client.put(f"/api/v1/mandates/{mandate_id}/fees", json=terms, headers=actor.headers)


async def get_fees(actor, mandate_id: int):
    return await actor.client.get(f"/api/v1/mandates/{mandate_id}/fees", headers=actor.headers)


async def record_invoice(world, mandate_id: int, **body):
    invoice = {"type": "retainer", "amount": "10000", "sent_date": "2026-10-01", "paid_date": "2026-10-05", **body}
    return await world.compliance.client.post(
        f"/api/v1/mandates/{mandate_id}/invoices", json=invoice, headers=world.compliance.headers
    )


async def close_won(world, mandate_id: int, final_ev: str):
    current = (await world.partner.client.get(f"/api/v1/mandates/{mandate_id}", headers=world.partner.headers)).json()
    return await world.partner.client.post(
        f"/api/v1/mandates/{mandate_id}/close",
        json={
            "version": current["version"],
            "outcome": "closed_won",
            "final_ev": final_ev,
            "buyer": "Northwind Capital",
            "ev_ebitda": "8",
            "closing_date": "2026-10-09",
            "tombstone_allowed": False,
        },
        headers=world.partner.headers,
    )


async def engage(world, mandate_id: int) -> None:
    response = await world.partner.client.post(
        f"/api/v1/mandates/{mandate_id}/links",
        json={"label": "Engagement letter", "url": "https://files.example.com/el.pdf"},
        headers=world.partner.headers,
    )
    assert response.status_code == 201, response.text


# DEAL-05 c1: retainer, % / fixed / minimum / Lehman tiers -> expected fee from the current estimated EV.
async def test_expected_fee_is_calculated_from_the_current_estimated_ev(world):
    mandate_id = await deal(world, ev="25000")

    saved = await put_fees(world.partner, mandate_id, success_fee_percent="2")
    assert saved.status_code == 200, saved.text
    assert Decimal(saved.json()["expected_fee"]) == Decimal("500000.00")
    assert Decimal(saved.json()["retainer_monthly"]) == Decimal("10000.00")

    current = (await world.partner.client.get(f"/api/v1/mandates/{mandate_id}", headers=world.partner.headers)).json()
    await world.partner.client.patch(
        f"/api/v1/mandates/{mandate_id}",
        json={"version": current["version"], "estimated_ev": "30000"},
        headers=world.partner.headers,
    )
    assert Decimal((await get_fees(world.partner, mandate_id)).json()["expected_fee"]) == Decimal("600000.00")

    fixed = await put_fees(world.partner, mandate_id, success_fee_kind="fixed", success_fee_fixed="250000")
    assert Decimal(fixed.json()["expected_fee"]) == Decimal("250000.00")

    floor = await put_fees(world.partner, mandate_id, success_fee_percent="1", minimum_fee="400000")
    assert Decimal(floor.json()["expected_fee"]) == Decimal("400000.00")

    lehman = await put_fees(
        world.partner,
        mandate_id,
        success_fee_kind="lehman",
        lehman_tiers=[{"up_to": "10000", "percent": "3"}, {"up_to": "20000", "percent": "2"}, {"up_to": None, "percent": "1"}],
    )
    assert lehman.status_code == 200, lehman.text
    # 3% of the first 10m + 2% of the next 10m + 1% of the last 10m of a 30m EV.
    assert Decimal(lehman.json()["expected_fee"]) == Decimal("600000.00")


async def test_lehman_tiers_must_ascend_and_end_open():
    with pytest.raises(ValueError, match="ascend"):
        FeeTermsValues(
            success_fee_kind="lehman",
            lehman_tiers=[
                {"up_to": "20000", "percent": "2"},
                {"up_to": "10000", "percent": "1"},
                {"up_to": None, "percent": "1"},
            ],
        )
    with pytest.raises(ValueError, match="open band"):
        FeeTermsValues(success_fee_kind="lehman", lehman_tiers=[{"up_to": "1000", "percent": "5"}])
    terms = FeeTermsValues(
        success_fee_kind="lehman", lehman_tiers=[{"up_to": "1000", "percent": "5"}, {"up_to": None, "percent": "1"}]
    )
    # EV is in EUR thousands, fees in EUR: 5% of 1m + 1% of the next 1m.
    assert expected_success_fee(terms, Decimal("2000")) == Decimal("60000.00")


# DEAL-05 c2 + REP-07 c2: closing computes the final fee and gives back-office an invoice task,
# which recording the success-fee invoice completes.
async def test_closing_computes_final_fee_and_invoice_task_is_completed_by_the_invoice(world):
    mandate_id = await deal(world, ev="25000")
    await put_fees(world.partner, mandate_id, success_fee_percent="2")

    closed = await close_won(world, mandate_id, final_ev="31000")
    assert closed.status_code == 200, closed.text

    fees = (await get_fees(world.compliance, mandate_id)).json()
    assert Decimal(fees["final_fee"]) == Decimal("620000.00")
    tasks = (await world.compliance.client.get("/api/v1/tasks/mine", headers=world.compliance.headers)).json()
    invoice_tasks = [task for task in tasks if task["record_id"] == mandate_id]
    assert len(invoice_tasks) == 1
    assert "Falcon" in invoice_tasks[0]["title"]
    assert "Acme" not in invoice_tasks[0]["title"]
    assert not any(email for email in world.emails.sent if "Acme" in email.body or "Acme" in email.subject)

    recorded = await record_invoice(world, mandate_id, type="success_fee", amount="620000", paid_date=None)
    assert recorded.status_code == 201, recorded.text
    done = (await world.compliance.client.get("/api/v1/tasks/mine?include_done=true", headers=world.compliance.headers)).json()
    assert [task["completed_at"] is not None for task in done if task["record_id"] == mandate_id] == [True]


# DEAL-05 c3: after engagement a fee change needs a reason and the amended letter link.
async def test_fee_change_after_engagement_needs_reason_and_amended_letter(world):
    mandate_id = await deal(world)
    await put_fees(world.partner, mandate_id, success_fee_percent="2")
    await engage(world, mandate_id)

    no_reason = await put_fees(world.partner, mandate_id, success_fee_percent="3")
    assert no_reason.status_code == 422
    assert {error["field"] for error in no_reason.json()["errors"]} >= {"change_reason"}

    no_link = await put_fees(world.partner, mandate_id, success_fee_percent="3", change_reason="Client renegotiated")
    assert no_link.status_code == 422
    assert {error["field"] for error in no_link.json()["errors"]} >= {"amended_letter_url"}

    saved = await put_fees(
        world.partner,
        mandate_id,
        success_fee_percent="3",
        change_reason="Client renegotiated",
        amended_letter_url="https://files.example.com/el-v2.pdf",
    )
    assert saved.status_code == 200, saved.text
    links = (await world.partner.client.get(f"/api/v1/mandates/{mandate_id}/links", headers=world.partner.headers)).json()
    assert ("Amended engagement letter", "https://files.example.com/el-v2.pdf") in {(x["label"], x["url"]) for x in links}
    entry = (
        await world.db.execute(
            select(AuditEntry).where(AuditEntry.action == "fee.changed", AuditEntry.record_id == str(mandate_id))
        )
    ).scalar_one()
    assert entry.new_values["change_reason"] == "Client renegotiated"
    assert entry.old_values["success_fee_percent"] == "2.00"

    unchanged = await put_fees(world.partner, mandate_id, success_fee_percent="3")
    assert unchanged.status_code == 200, unchanged.text


# DEAL-05 c4: creditable retainers come off the final fee.
async def test_creditable_retainers_are_deducted_from_the_final_fee(world):
    mandate_id = await deal(world, ev="10000")
    await put_fees(world.partner, mandate_id, success_fee_percent="3", retainers_creditable=True)
    await record_invoice(world, mandate_id, amount="10000")
    await record_invoice(world, mandate_id, amount="10000", sent_date="2026-10-02")
    await record_invoice(world, mandate_id, amount="10000", sent_date="2026-10-03", paid_date=None)

    fees = (await get_fees(world.partner, mandate_id)).json()
    assert Decimal(fees["retainers_paid"]) == Decimal("20000.00")
    assert Decimal(fees["expected_fee"]) == Decimal("280000.00")

    await close_won(world, mandate_id, final_ev="10000")
    assert Decimal((await get_fees(world.partner, mandate_id)).json()["final_fee"]) == Decimal("280000.00")


async def test_without_the_box_retainers_are_not_deducted(world):
    mandate_id = await deal(world, ev="10000")
    await put_fees(world.partner, mandate_id, success_fee_percent="3", retainers_creditable=False)
    await record_invoice(world, mandate_id, amount="10000")
    await close_won(world, mandate_id, final_ev="10000")
    assert Decimal((await get_fees(world.partner, mandate_id)).json()["final_fee"]) == Decimal("300000.00")


# AUTHZ-06 c1: analysts see no fee field in the API or exports (the UI follows the API).
async def test_analyst_gets_no_fee_fields_in_api_or_exports(world):
    mandate_id = await deal(world)
    await put_fees(world.partner, mandate_id)
    analyst = world.analyst

    assert (await get_fees(analyst, mandate_id)).status_code == 403
    assert (await analyst.client.get(f"/api/v1/mandates/{mandate_id}/invoices", headers=analyst.headers)).status_code == 403
    assert (await analyst.client.get("/api/v1/fees/", headers=analyst.headers)).status_code == 403
    assert (await analyst.client.get("/api/v1/fees/export", headers=analyst.headers)).status_code == 403
    for path in (f"/api/v1/mandates/{mandate_id}", "/api/v1/mandates/", f"/api/v1/mandates/{mandate_id}/history"):
        body = (await analyst.client.get(path, headers=analyst.headers)).text
        assert not [key for key in FEE_KEYS if key in body], (path, body)

    export = await world.partner.client.get("/api/v1/fees/export", headers=world.partner.headers)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "Falcon" in export.text
    assert "500000.00" in export.text
    audit = (await world.db.execute(select(AuditEntry).where(AuditEntry.action == "export"))).scalars().all()
    assert any(entry.new_values.get("kind") == "fees" for entry in audit)


# AUTHZ-06 c2: compliance sees the fee fields but not the deal notes.
async def test_compliance_sees_fees_but_not_deal_notes(world):
    mandate_id = await deal(world)
    await put_fees(world.partner, mandate_id)
    note = await world.partner.client.post(
        "/api/v1/notes/",
        json={"record_type": "mandate", "record_id": mandate_id, "body": "Seller is nervous", "visibility": "shared"},
        headers=world.partner.headers,
    )
    assert note.status_code == 201, note.text

    fees = await get_fees(world.compliance, mandate_id)
    assert fees.status_code == 200
    assert Decimal(fees.json()["expected_fee"]) == Decimal("500000.00")
    timeline = await world.compliance.client.get(f"/api/v1/timeline/mandate/{mandate_id}", headers=world.compliance.headers)
    assert timeline.status_code == 404
    assert "nervous" not in timeline.text


# AUTHZ-06 c3: a fee filter is not offered to a role that cannot see fees.
async def test_fee_filter_is_not_offered_without_fee_visibility(world):
    small = await deal(world, ev="1000")
    await put_fees(world.partner, small, success_fee_percent="1")
    large = await create_mandate(world, world.partner, world.client_id, code_name="Heron", estimated_ev="90000")
    await staff(world, large["id"], world.analyst, "analyst")
    await put_fees(world.partner, large["id"], success_fee_percent="1")

    filtered = await world.partner.client.get("/api/v1/fees/?min_expected_fee=100000", headers=world.partner.headers)
    assert [row["code_name"] for row in filtered.json()] == ["Heron"]
    offered = await world.partner.client.get("/api/v1/mandates/filters", headers=world.partner.headers)
    assert "min_expected_fee" in offered.json()["filters"]

    assert (
        await world.analyst.client.get("/api/v1/fees/?min_expected_fee=1", headers=world.analyst.headers)
    ).status_code == 403
    offered = await world.analyst.client.get("/api/v1/mandates/filters", headers=world.analyst.headers)
    assert "min_expected_fee" not in offered.json()["filters"]
    assert {"partner_id", "type", "sector_id", "stage"} <= set(offered.json()["filters"])


async def test_unstaffed_partner_cannot_list_or_filter_other_deals_fees(world):
    mandate_id = await deal(world)
    await put_fees(world.partner, mandate_id)
    listed = await world.outsider.client.get("/api/v1/fees/", headers=world.outsider.headers)
    assert listed.status_code == 200
    assert listed.json() == []


# AUTHZ-06 c4: an admin's change of field visibility per role is audited (and takes effect).
async def test_admin_changing_fee_visibility_per_role_is_audited(world):
    roles = (await world.admin.client.get("/api/v1/roles/", headers=world.admin.headers)).json()
    analyst_role = next(role for role in roles if role["name"] == RoleName.ANALYST.value)
    granted = await world.admin.client.put(
        f"/api/v1/roles/{analyst_role['id']}/permissions",
        json={"permissions": [*analyst_role["permissions"], "fees.read"]},
        headers=world.admin.headers,
    )
    assert granted.status_code == 200, granted.text

    entry = (
        await world.db.execute(
            select(AuditEntry).where(
                AuditEntry.action == "role.permissions_changed", AuditEntry.record_id == str(analyst_role["id"])
            )
        )
    ).scalar_one()
    assert "fees.read" in entry.new_values["permissions"]
    assert "fees.read" not in entry.old_values["permissions"]
    assert entry.user_id == world.admin.id

    mandate_id = await deal(world)
    await put_fees(world.partner, mandate_id)
    assert (await get_fees(world.analyst, mandate_id)).status_code == 200
    assert (await put_fees(world.analyst, mandate_id)).status_code == 403


# REP-07 c1: invoices are stored on the mandate and visible only to roles that see fee fields.
async def test_invoices_are_stored_on_the_mandate_and_hidden_like_fees(world):
    mandate_id = await deal(world)
    recorded = await record_invoice(world, mandate_id, type="retainer", amount="10000")
    assert recorded.status_code == 201, recorded.text
    marked = await world.compliance.client.patch(
        f"/api/v1/mandates/{mandate_id}/invoices/{recorded.json()['id']}",
        json={"paid_date": "2026-10-08"},
        headers=world.compliance.headers,
    )
    assert marked.status_code == 200, marked.text

    for reader in (world.partner, world.compliance):
        invoices = (await reader.client.get(f"/api/v1/mandates/{mandate_id}/invoices", headers=reader.headers)).json()
        assert [(i["type"], i["amount"], i["sent_date"], i["paid_date"]) for i in invoices] == [
            ("retainer", "10000.00", "2026-10-01", "2026-10-08")
        ]
    for hidden in (world.analyst, world.director):
        response = await hidden.client.get(f"/api/v1/mandates/{mandate_id}/invoices", headers=hidden.headers)
        assert response.status_code == 403
    response = await world.outsider.client.get(f"/api/v1/mandates/{mandate_id}/invoices", headers=world.outsider.headers)
    assert response.status_code == 404
    partner_records = await world.partner.client.post(
        f"/api/v1/mandates/{mandate_id}/invoices",
        json={"type": "retainer", "amount": "1", "sent_date": "2026-10-01"},
        headers=world.partner.headers,
    )
    assert partner_records.status_code == 403


# ROLE-01 c4: compliance on a deal it is not staffed on sees a read-only summary plus fee and invoice fields.
async def test_compliance_unstaffed_sees_read_only_summary_fees_and_invoices(world):
    mandate_id = await deal(world)
    await put_fees(world.partner, mandate_id)
    await record_invoice(world, mandate_id)
    compliance = world.compliance

    summary = await compliance.client.get(f"/api/v1/mandates/{mandate_id}/summary", headers=compliance.headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["code_name"] == "Falcon"
    assert (summary.json()["can_edit"], summary.json()["can_manage_team"], summary.json()["can_close"]) == (False, False, False)
    assert (await get_fees(compliance, mandate_id)).status_code == 200
    assert len((await compliance.client.get(f"/api/v1/mandates/{mandate_id}/invoices", headers=compliance.headers)).json()) == 1
    current = summary.json()
    edit = await compliance.client.patch(
        f"/api/v1/mandates/{mandate_id}", json={"version": current["version"], "estimated_ev": "1"}, headers=compliance.headers
    )
    assert edit.status_code == 404

    for outsider in (world.outsider, world.admin):
        response = await outsider.client.get(f"/api/v1/mandates/{mandate_id}/summary", headers=outsider.headers)
        assert response.status_code == 404


# ROLE-01 c5: a partner edits fees only on deals where they are on the deal team.
async def test_partner_edits_fees_only_on_staffed_deals(world):
    mandate_id = await deal(world)
    assert (await put_fees(world.partner, mandate_id)).status_code == 200
    assert (await put_fees(world.outsider, mandate_id)).status_code == 404
    assert (await put_fees(world.director, mandate_id)).status_code == 403

    await staff(world, mandate_id, world.outsider, "partner")
    assert (await put_fees(world.outsider, mandate_id, success_fee_percent="2.5")).status_code == 200
