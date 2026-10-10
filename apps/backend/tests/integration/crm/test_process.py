"""Offers and bid comparison (BUY-05), process letters (BUY-06), the funnel (BUY-07), templates (ADM-07),
the client status report (REP-05), contact language/salutation in templates (CON-01 c3), opted-out contacts excluded
from mailings (GDPR-01 c2) and the full deal page (DEAL-03 c1)."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.modules.activity.models import Activity, ActivityLink
from src.modules.audit.models import AuditEntry
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.director = await built.actor("dirk", RoleName.DIRECTOR)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.client_id = await built.company("Acme Holding")
    built.target_id = await built.company("Widget Works")
    yield built
    await built.close()
    set_clock(SystemClock())


async def get(actor, path: str, **params):
    return await actor.client.get(path, headers=actor.headers, params=params)


async def send(actor, method: str, path: str, body: dict | None = None):
    return await actor.client.request(method, path, json=body, headers=actor.headers)


async def deal(world) -> int:
    mandate = await create_mandate(world, world.partner, world.client_id, target_id=world.target_id)
    for actor, role in ((world.director, "director"), (world.analyst, "analyst")):
        response = await send(
            world.partner, "POST", f"/api/v1/mandates/{mandate['id']}/team", {"user_id": actor.id, "role": role}
        )
        assert response.status_code == 201, response.text
    return mandate["id"]


async def contact(world, company_id: int, first: str, **values) -> int:
    body = {
        "first_name": first,
        "last_name": "Buyer",
        "source": "Forum",
        "company_id": company_id,
        "email": f"{first}@buyer.eu",
    }
    response = await send(world.partner, "POST", "/api/v1/contacts/", {**body, **values})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def buyer(world, mandate_id: int, name: str, contact_values: dict | None = None, nda_signed: bool = True) -> int:
    company_id = await world.company(name, "financial_investor")
    contact_id = await contact(world, company_id, name.split()[0], **(contact_values or {}))
    response = await send(
        world.director,
        "POST",
        f"/api/v1/mandates/{mandate_id}/buyers",
        {"items": [{"company_id": company_id, "owner_id": world.director.id, "rationale": "Fit", "contact_id": contact_id}]},
    )
    assert response.status_code == 200, response.text
    [buyer_id] = response.json()["added"]
    approved = await send(world.director, "PATCH", f"/api/v1/mandates/{mandate_id}/buyers/{buyer_id}", {"approval": "approved"})
    assert approved.status_code == 200, approved.text
    if nda_signed:
        nda = {"sent_date": "2026-09-01", "signed_date": "2026-09-10"}
        response = await send(world.director, "PUT", f"/api/v1/mandates/{mandate_id}/buyers/{buyer_id}/nda", nda)
        assert response.status_code == 200, response.text
    return buyer_id


def offer_body(buyer_id: int, ev: str, **values) -> dict:
    return {
        "buyer_id": buyer_id,
        "round": "indicative",
        "ev": ev,
        "equity_value": str(float(ev) - 5),
        "cash_pct": "80",
        "earn_out_pct": "10",
        "vendor_loan_pct": "5",
        "rollover_pct": "5",
        "conditions": "Confirmatory due diligence",
        "financing_certainty": "committed",
        **values,
    }


async def offer(world, mandate_id: int, buyer_id: int, ev: str, actor=None, **values) -> dict:
    response = await send(
        actor or world.director, "POST", f"/api/v1/mandates/{mandate_id}/offers", offer_body(buyer_id, ev, **values)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def template(world, name: str, language: str, subject: str, body: str, kind: str = "letter", **values) -> dict:
    payload = {"kind": kind, "name": name, "language": language, "subject": subject, "body": body, **values}
    response = await send(world.admin, "POST", "/api/v1/templates/", payload)
    assert response.status_code == 201, response.text
    return response.json()


async def letter_templates(world, name: str = "Process letter", references_im: bool = False) -> None:
    await template(
        world,
        name,
        "en",
        "{{code_name}}: next phase",
        "{{salutation}} {{last_name}},\nBest regards",
        references_im=references_im,
    )
    await template(
        world,
        name,
        "fr",
        "{{code_name}} : phase suivante",
        "{{salutation}} {{last_name}},\nCordialement",
        references_im=references_im,
    )
    await template(
        world,
        name,
        "nl",
        "{{code_name}}: volgende fase",
        "{{salutation}} {{last_name}},\nMet vriendelijke groet",
        references_im=references_im,
    )


# BUY-05


async def test_buy05_c1_an_offer_with_structure_conditions_and_financing_shows_in_the_comparison(world):
    mandate_id = await deal(world)
    buyer_id = await buyer(world, mandate_id, "Northstar Capital")

    await offer(world, mandate_id, buyer_id, "42.5")
    comparison = (await get(world.director, f"/api/v1/mandates/{mandate_id}/offers")).json()

    [bid] = comparison["bids"]
    assert bid["buyer_name"] == "Northstar Capital"
    assert (bid["ev"], bid["equity_value"]) == ("42.50", "37.50")
    assert (bid["cash_pct"], bid["earn_out_pct"], bid["vendor_loan_pct"], bid["rollover_pct"]) == (
        "80.00",
        "10.00",
        "5.00",
        "5.00",
    )
    assert bid["conditions"] == "Confirmatory due diligence"
    assert bid["financing_certainty"] == "committed"


async def test_buy05_c1_the_structure_must_add_up_to_100_percent(world):
    mandate_id = await deal(world)
    buyer_id = await buyer(world, mandate_id, "Northstar Capital")

    response = await send(
        world.director, "POST", f"/api/v1/mandates/{mandate_id}/offers", offer_body(buyer_id, "40", cash_pct="90")
    )

    assert response.status_code == 422


async def test_buy05_c2_bids_sort_by_ev_with_implied_ev_ebitda(world):
    mandate_id = await deal(world)
    figures = await send(world.partner, "PUT", f"/api/v1/companies/{world.target_id}/financials/2025", {"ebitda": "5000"})
    assert figures.status_code == 200, figures.text
    low = await buyer(world, mandate_id, "Lowball Partners")
    high = await buyer(world, mandate_id, "Highball Capital")
    middle = await buyer(world, mandate_id, "Middle Equity")
    await offer(world, mandate_id, low, "30")
    await offer(world, mandate_id, high, "55")
    await offer(world, mandate_id, middle, "42")

    comparison = (await get(world.director, f"/api/v1/mandates/{mandate_id}/offers")).json()

    assert [bid["buyer_name"] for bid in comparison["bids"]] == ["Highball Capital", "Middle Equity", "Lowball Partners"]
    assert [bid["ev_ebitda"] for bid in comparison["bids"]] == ["11.0", "8.4", "6.0"]
    assert (comparison["ebitda"], comparison["ebitda_year"]) == ("5000.00", 2025)


async def test_buy05_c3_analysts_see_offer_values(world):
    mandate_id = await deal(world)
    buyer_id = await buyer(world, mandate_id, "Northstar Capital")
    await offer(world, mandate_id, buyer_id, "42.5")

    response = await get(world.analyst, f"/api/v1/mandates/{mandate_id}/offers")

    assert response.status_code == 200
    assert response.json()["bids"][0]["ev"] == "42.50"
    assert response.json()["bids"][0]["equity_value"] == "37.50"


async def test_buy05_c4_a_revised_offer_keeps_earlier_versions_with_dates(world):
    mandate_id = await deal(world)
    buyer_id = await buyer(world, mandate_id, "Northstar Capital")
    await offer(world, mandate_id, buyer_id, "40")
    set_clock(FrozenClock(NOW + timedelta(days=3)))
    await offer(world, mandate_id, buyer_id, "44")

    comparison = (await get(world.director, f"/api/v1/mandates/{mandate_id}/offers")).json()

    [bid] = comparison["bids"]
    assert (bid["version"], bid["ev"]) == (2, "44.00")
    assert [(item["version"], item["ev"], item["entered_at"][:10]) for item in comparison["history"]] == [
        (2, "44.00", "2026-10-12"),
        (1, "40.00", "2026-10-09"),
    ]


async def test_buy05_c5_an_offer_after_the_bid_deadline_is_flagged_late(world):
    mandate_id = await deal(world)
    buyer_id = await buyer(world, mandate_id, "Northstar Capital")
    deadlines = {"indicative_at": (NOW - timedelta(hours=1)).isoformat(), "binding_at": (NOW + timedelta(days=30)).isoformat()}
    assert (await send(world.director, "PUT", f"/api/v1/mandates/{mandate_id}/bid-deadlines", deadlines)).status_code == 200

    late = await offer(world, mandate_id, buyer_id, "40")
    on_time = await offer(world, mandate_id, buyer_id, "41", round="binding")
    early = await offer(world, mandate_id, buyer_id, "42", received_at=(NOW - timedelta(hours=2)).isoformat())

    assert late["late"] is True
    assert on_time["late"] is False
    assert early["late"] is False


# ADM-07, CON-01 c3


async def test_adm07_c1_templates_with_merge_fields_are_stored_per_language(world):
    await letter_templates(world)

    rows = (await get(world.admin, "/api/v1/templates/")).json()
    names = (await get(world.director, "/api/v1/templates/names")).json()

    assert sorted(row["language"] for row in rows) == ["en", "fr", "nl"]
    assert {row["name"] for row in rows} == {"Process letter"}
    assert names == [{"kind": "letter", "name": "Process letter", "languages": ["en", "fr", "nl"]}]


async def test_adm07_c1_unknown_merge_fields_are_refused_and_only_admins_manage_templates(world):
    bad = await send(
        world.admin,
        "POST",
        "/api/v1/templates/",
        {"kind": "letter", "name": "X", "language": "en", "subject": "S", "body": "{{fee}}"},
    )
    by_director = await send(
        world.director,
        "POST",
        "/api/v1/templates/",
        {"kind": "letter", "name": "X", "language": "en", "subject": "S", "body": "B"},
    )

    assert bad.status_code == 422
    assert "fee" in bad.text
    assert by_director.status_code == 403


async def test_adm07_c2_a_template_change_is_audited_and_earlier_documents_keep_their_text(world, seeded_db):
    mandate_id = await deal(world)
    buyer_id = await buyer(world, mandate_id, "Northstar Capital", {"salutation": "Dear Ms", "language": "en"})
    created = await template(world, "Process letter", "en", "{{code_name}} update", "{{salutation}} {{last_name}}, version one")
    sent = (
        await send(
            world.director,
            "POST",
            f"/api/v1/mandates/{mandate_id}/letters",
            {"template_name": "Process letter", "buyer_ids": [buyer_id]},
        )
    ).json()

    edit = {**{k: created[k] for k in ("kind", "name", "language", "subject", "references_im")}, "body": "Version two"}
    updated = await send(world.admin, "PUT", f"/api/v1/templates/{created['id']}", edit)
    documents = (await get(world.director, f"/api/v1/mandates/{mandate_id}/documents")).json()

    assert updated.status_code == 200
    audit = (await seeded_db.execute(select(AuditEntry).where(AuditEntry.action == "template.updated"))).scalar_one()
    assert audit.old_values["body"] == "{{salutation}} {{last_name}}, version one"
    assert audit.new_values["body"] == "Version two"
    assert [document["body"] for document in documents] == ["Dear Ms Buyer, version one"]
    assert sent["sent"][0]["document_id"] == documents[0]["id"]


async def test_con01_c3_letters_use_each_contacts_language_and_salutation(world):
    mandate_id = await deal(world)
    en = await buyer(world, mandate_id, "Albion Capital", {"salutation": "Dear Mr", "language": "en"})
    fr = await buyer(world, mandate_id, "Bastille Partenaires", {"salutation": "Cher Monsieur", "language": "fr"})
    nl = await buyer(world, mandate_id, "Dijk Investeringen", {"salutation": "Geachte heer", "language": "nl"})
    await letter_templates(world)

    result = (
        await send(
            world.director,
            "POST",
            f"/api/v1/mandates/{mandate_id}/letters",
            {"template_name": "Process letter", "buyer_ids": [en, fr, nl]},
        )
    ).json()

    by_buyer = {item["buyer_id"]: item for item in result["sent"]}
    assert by_buyer[en]["body"] == "Dear Mr Buyer,\nBest regards"
    assert by_buyer[fr]["body"] == "Cher Monsieur Buyer,\nCordialement"
    assert by_buyer[fr]["subject"] == "Falcon : phase suivante"
    assert by_buyer[nl]["body"] == "Geachte heer Buyer,\nMet vriendelijke groet"
    assert [by_buyer[b]["language"] for b in (en, fr, nl)] == ["en", "fr", "nl"]


# BUY-06, GDPR-01 c2


async def test_buy06_c1_each_buyer_gets_a_merged_letter_and_the_send_is_logged_as_an_activity(world, seeded_db):
    mandate_id = await deal(world)
    first = await buyer(world, mandate_id, "Albion Capital", {"salutation": "Dear Mr"})
    second = await buyer(world, mandate_id, "Northstar Capital", {"salutation": "Dear Ms"})
    await letter_templates(world)

    response = await send(
        world.director,
        "POST",
        f"/api/v1/mandates/{mandate_id}/letters",
        {"template_name": "Process letter", "buyer_ids": [first, second]},
    )

    assert response.status_code == 200, response.text
    assert [(item["contact_name"], item["subject"]) for item in response.json()["sent"]] == [
        ("Albion Buyer", "Falcon: next phase"),
        ("Northstar Buyer", "Falcon: next phase"),
    ]
    assert sorted(email.to for email in world.emails.sent if "next phase" in email.subject) == [
        "Albion@buyer.eu",
        "Northstar@buyer.eu",
    ]
    activities = list((await seeded_db.execute(select(Activity).where(Activity.note.like("Process letter sent:%")))).scalars())
    assert len(activities) == 2
    links = {
        (link.record_type, link.record_id)
        for link in (
            await seeded_db.execute(select(ActivityLink).where(ActivityLink.activity_id == activities[0].id))
        ).scalars()
    }
    assert ("mandate", mandate_id) in links
    timeline = (await get(world.director, f"/api/v1/timeline/mandate/{mandate_id}")).json()
    assert sum(1 for item in timeline["activities"] if item["note"].startswith("Process letter sent")) == 2


async def test_buy06_c2_a_letter_referencing_the_im_excludes_buyers_without_a_signed_nda_and_says_why(world):
    mandate_id = await deal(world)
    signed = await buyer(world, mandate_id, "Albion Capital")
    unsigned = await buyer(world, mandate_id, "Northstar Capital", nda_signed=False)
    await letter_templates(world, "IM letter", references_im=True)

    result = (
        await send(
            world.director,
            "POST",
            f"/api/v1/mandates/{mandate_id}/letters",
            {"template_name": "IM letter", "buyer_ids": [signed, unsigned]},
        )
    ).json()

    assert [item["buyer_id"] for item in result["sent"]] == [signed]
    [excluded] = result["excluded"]
    assert excluded["buyer_id"] == unsigned
    assert excluded["reason"] == "no_signed_nda"
    assert "NDA" in excluded["message"]


async def test_buy06_c2_a_letter_without_the_im_reaches_buyers_without_an_nda(world):
    mandate_id = await deal(world)
    unsigned = await buyer(world, mandate_id, "Northstar Capital", nda_signed=False)
    await letter_templates(world)

    result = (
        await send(
            world.director,
            "POST",
            f"/api/v1/mandates/{mandate_id}/letters",
            {"template_name": "Process letter", "buyer_ids": [unsigned]},
        )
    ).json()

    assert [item["buyer_id"] for item in result["sent"]] == [unsigned]


async def test_gdpr01_c2_opted_out_contacts_are_excluded_from_mailings_automatically(world):
    mandate_id = await deal(world)
    kept = await buyer(world, mandate_id, "Albion Capital")
    opted_out = await buyer(world, mandate_id, "Northstar Capital", {"marketing_opt_out": True})
    await letter_templates(world)

    result = (
        await send(
            world.director,
            "POST",
            f"/api/v1/mandates/{mandate_id}/letters",
            {"template_name": "Process letter", "buyer_ids": [kept, opted_out]},
        )
    ).json()

    assert [item["buyer_id"] for item in result["sent"]] == [kept]
    assert [(item["buyer_id"], item["reason"]) for item in result["excluded"]] == [(opted_out, "opted_out")]
    assert not [email for email in world.emails.sent if email.to == "Northstar@buyer.eu"]


# BUY-07


async def test_buy07_c1_the_funnel_shows_counts_and_conversion_per_status_and_exports_to_pdf(world, seeded_db):
    mandate_id = await deal(world)
    ids = [
        await buyer(world, mandate_id, name, nda_signed=i < 3)
        for i, name in enumerate(("Alpha Capital", "Bravo Equity", "Charlie Partners", "Delta Invest"))
    ]
    status = {"buyer_ids": ids[:2], "status": "im_sent"}
    assert (await send(world.director, "POST", f"/api/v1/mandates/{mandate_id}/buyers/status", status)).status_code == 200
    await offer(world, mandate_id, ids[0], "40")
    await offer(world, mandate_id, ids[0], "41", round="binding")
    await send(
        world.director, "POST", f"/api/v1/mandates/{mandate_id}/buyers/status", {"buyer_ids": [ids[3]], "status": "contacted"}
    )

    funnel = (await get(world.partner, f"/api/v1/mandates/{mandate_id}/funnel")).json()
    exported = await get(world.partner, f"/api/v1/mandates/{mandate_id}/funnel.pdf")

    assert [(step["key"], step["count"], step["conversion_pct"]) for step in funnel["steps"]] == [
        ("approached", 4, "100.0"),
        ("nda", 3, "75.0"),
        ("im", 2, "66.7"),
        ("offers", 1, "50.0"),
        ("binding", 1, "100.0"),
    ]
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/pdf"
    assert exported.content.startswith(b"%PDF")
    assert (await seeded_db.execute(select(AuditEntry).where(AuditEntry.action == "export"))).scalars().first() is not None


# REP-05


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)


async def test_rep05_c1_the_report_has_funnel_timeline_and_next_steps_and_no_notes_or_fees(world):
    mandate_id = await deal(world)
    buyer_id = await buyer(world, mandate_id, "Northstar Capital")
    await send(world.director, "PATCH", f"/api/v1/mandates/{mandate_id}/buyers/{buyer_id}", {"notes": "Secret view on price"})
    await offer(world, mandate_id, buyer_id, "42.5")
    fees = await send(
        world.partner, "PUT", f"/api/v1/mandates/{mandate_id}/fees", {"retainer_monthly": "12345", "success_fee_percent": "2"}
    )
    assert fees.status_code == 200, fees.text
    note = await send(
        world.partner, "POST", "/api/v1/notes/", {"record_type": "mandate", "record_id": mandate_id, "body": "Internal gossip"}
    )
    assert note.status_code == 201, note.text
    await send(
        world.director,
        "POST",
        f"/api/v1/mandates/{mandate_id}/milestones",
        {"name": "Teaser", "planned_date": "2026-09-15", "actual_date": "2026-09-20"},
    )
    await send(
        world.director,
        "POST",
        f"/api/v1/mandates/{mandate_id}/milestones",
        {"name": "Binding offers", "planned_date": "2026-11-15"},
    )

    response = await send(world.director, "POST", f"/api/v1/mandates/{mandate_id}/status-report")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    text = pdf_text(response.content)
    assert "Process funnel" in text
    assert "Approached: 1" in text
    assert "Teaser: planned 2026-09-15, actual 2026-09-20" in text
    assert "2026-11-15: Binding offers" in text
    for leaked in ("Secret view", "Internal gossip", "12345", "42.5", "Northstar", "fee"):
        assert leaked not in text


async def test_rep05_c2_the_report_uses_the_clients_language_and_firm_template_and_is_logged(world, seeded_db):
    mandate_id = await deal(world)
    assert (await send(world.partner, "PATCH", f"/api/v1/companies/{world.client_id}", {"language": "fr"})).status_code == 200
    await template(
        world, "Status report", "fr", "Rapport {{code_name}}", "Cabinet Merlin\n{{funnel}}\n{{next_steps}}", kind="report"
    )
    await template(world, "Status report", "en", "Report {{code_name}}", "Merlin firm\n{{funnel}}", kind="report")

    response = await send(world.director, "POST", f"/api/v1/mandates/{mandate_id}/status-report")

    text = pdf_text(response.content)
    assert "Rapport Falcon" in text
    assert "Cabinet Merlin" in text
    assert "Approchés: 0" in text
    assert "Merlin firm" not in text
    [document] = (await get(world.director, f"/api/v1/mandates/{mandate_id}/documents")).json()
    assert (document["kind"], document["language"]) == ("report", "fr")
    timeline = (await get(world.director, f"/api/v1/timeline/mandate/{mandate_id}")).json()
    assert [item["note"] for item in timeline["activities"]] == ["Client status report generated: Rapport Falcon"]


async def test_rep05_the_report_is_refused_to_anyone_off_the_team(world):
    mandate_id = await deal(world)
    outsider = await world.actor("oscar", RoleName.PARTNER)

    assert (await send(outsider, "POST", f"/api/v1/mandates/{mandate_id}/status-report")).status_code == 404


# DEAL-03 c1


async def test_deal03_c1_the_deal_page_serves_every_section(world):
    mandate_id = await deal(world)
    await send(
        world.director,
        "POST",
        "/api/v1/tasks/",
        {
            "title": "Call Northstar",
            "assignee_id": world.analyst.id,
            "due_date": "2026-10-20",
            "record_type": "mandate",
            "record_id": mandate_id,
        },
    )
    await send(
        world.director,
        "POST",
        "/api/v1/activities/",
        {
            "type": "call",
            "occurred_at": NOW.isoformat(),
            "note": "Kick-off",
            "links": [{"record_type": "mandate", "record_id": mandate_id}],
        },
    )
    await send(
        world.director,
        "POST",
        f"/api/v1/mandates/{mandate_id}/links",
        {"label": "VDR", "url": "https://vdr.example.com/falcon"},
    )
    await send(
        world.director, "POST", f"/api/v1/mandates/{mandate_id}/milestones", {"name": "Teaser", "planned_date": "2026-11-01"}
    )

    sections = {
        "summary": f"/api/v1/mandates/{mandate_id}",
        "team": f"/api/v1/mandates/{mandate_id}/team",
        "timeline": f"/api/v1/mandates/{mandate_id}/milestones",
        "buyers": f"/api/v1/mandates/{mandate_id}/buyers",
        "activities": f"/api/v1/timeline/mandate/{mandate_id}",
        "tasks": f"/api/v1/mandates/{mandate_id}/tasks",
        "documents": f"/api/v1/mandates/{mandate_id}/links",
        "fees": f"/api/v1/mandates/{mandate_id}/fees",
    }
    partner = {key: await get(world.partner, path) for key, path in sections.items()}
    analyst_fees = await get(world.analyst, sections["fees"])

    assert {key: response.status_code for key, response in partner.items()} == dict.fromkeys(sections, 200)
    assert [task["title"] for task in partner["tasks"].json()] == ["Call Northstar"]
    assert partner["tasks"].json()[0]["assignee_name"] == "anna"
    assert [item["note"] for item in partner["activities"].json()["activities"]] == ["Kick-off"]
    assert [link["label"] for link in partner["documents"].json()] == ["VDR"]
    assert analyst_fees.status_code == 403
