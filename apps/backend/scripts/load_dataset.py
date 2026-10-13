"""The NFR-02 load-test dataset: 50 users, 200,000 contacts and the deals they work on.

Set-based SQL (generate_series), so 200k contacts load in seconds. Shared by the load-test seed
script (`scripts/seed_load_test.py`) and the performance tests, so both measure the same shape.
"""

import hashlib
import secrets
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.api_access.service import PERSONAL_PREFIX, SHOWN_PREFIX_LENGTH

FIRST_NAMES = ["Anne", "Bart", "Claire", "Dirk", "Els", "François", "Geert", "Hélène", "Inge", "Jan", "Karel", "Lien"]
LAST_NAMES = ["Peeters", "Janssens", "Maes", "Dubois", "Lambert", "Wouters", "Claes", "Goossens", "Martin", "Willems"]
ROLE_MIX = (
    ["Partner"] * 10
    + ["Director / Manager"] * 15
    + ["Analyst / Associate"] * 20
    + ["Compliance / Back-office"] * 3
    + ["Read-only"] * 2
)
PASSWORD_HASH = "$2b$12$abcdefghijklmnopqrstuuJ6uH5cTnOq7v1zYz2lC8xXbYI5hPp0K"


@dataclass
class LoadDataset:
    user_ids: list[int] = field(default_factory=list)
    tokens: dict[int, str] = field(default_factory=dict)
    contacts: int = 0
    companies: int = 0
    deals: int = 0


async def _scalar(db: AsyncSession, sql: str, **values: object) -> int:
    return int((await db.execute(text(sql), values)).scalar_one())


async def seed_load_dataset(
    db: AsyncSession,
    *,
    users: int = 50,
    contacts: int = 200_000,
    companies: int = 20_000,
    deals: int = 2_000,
    team_size: int = 6,
    with_tokens: bool = True,
    tag: str = "load",
) -> LoadDataset:
    """Idempotent per `tag`: a second run adds nothing and returns the existing dataset."""
    dataset = LoadDataset()
    country = await _scalar(db, "SELECT id FROM picklist_values WHERE kind = 'country' ORDER BY id LIMIT 1")
    sector = (
        await db.execute(text("SELECT id FROM picklist_values WHERE kind = 'sector' ORDER BY id LIMIT 1"))
    ).scalar_one_or_none()
    if sector is None:
        sector = await _scalar(
            db,
            "INSERT INTO picklist_values (kind, code, label_en, label_fr, label_nl, is_active, created_at, updated_at) "
            "VALUES ('sector', :code, 'Technology', 'Technologie', 'Technologie', true, now(), now()) RETURNING id",
            code=f"{tag}-tech",
        )

    for index in range(users):
        email = f"{tag}.user{index:02d}@firm.example"
        existing = (await db.execute(text('SELECT id FROM "user" WHERE email = :email'), {"email": email})).scalar_one_or_none()
        if existing is None:
            existing = await _scalar(
                db,
                'INSERT INTO "user" (name, email, hashed_password, profile_image_url, role_id, email_verified, '
                "first_name, last_name, status, language, created_at, updated_at, is_deleted) "
                "VALUES (:name, :email, :hash, 'https://profileimageurl.com', "
                "(SELECT id FROM roles WHERE name = :role), true, :first, :last, 'active', :language, now(), now(), false) "
                "RETURNING id",
                name=f"{FIRST_NAMES[index % 12]} {LAST_NAMES[index % 10]}",
                email=email,
                hash=PASSWORD_HASH,
                role=ROLE_MIX[index % len(ROLE_MIX)],
                first=FIRST_NAMES[index % 12],
                last=LAST_NAMES[index % 10],
                language=("en", "fr", "nl")[index % 3],
            )
        dataset.user_ids.append(existing)
    partners = [uid for index, uid in enumerate(dataset.user_ids) if ROLE_MIX[index % len(ROLE_MIX)] == "Partner"]
    staffable = [
        uid
        for index, uid in enumerate(dataset.user_ids)
        if ROLE_MIX[index % len(ROLE_MIX)] in ("Partner", "Director / Manager", "Analyst / Associate")
    ]

    have_companies = await _scalar(db, "SELECT count(*) FROM companies WHERE vat_or_registry_number LIKE :tag", tag=f"{tag}-%")
    if have_companies < companies:
        await db.execute(
            text(
                "INSERT INTO companies (name, normalized_name, type, country_id, vat_or_registry_number, language, "
                "created_at, updated_at) "
                "SELECT n, lower(n), (ARRAY['target','strategic_buyer','financial_investor','other'])[1 + g % 4], "
                ":country, "
                "CAST(:tag AS text) || '-' || g, 'en', now(), now() "
                "FROM (SELECT g, (ARRAY['Alpha','Brabant','Cobalt','Delta','Escaut','Flandria','Gaume','Hainaut'])[1 + "
                "g % 8] "
                "|| ' ' || (ARRAY['Industries','Logistics','Foods','Systems','Partners','Capital','Labs','Energy'])[1 "
                "+ (g / 8) % 8] "
                "|| ' ' || g AS n FROM generate_series(CAST(:start AS integer), CAST(:stop AS integer)) AS g) s"
            ),
            {"country": country, "tag": tag, "start": have_companies + 1, "stop": companies},
        )
    first_company = await _scalar(db, "SELECT min(id) FROM companies WHERE vat_or_registry_number LIKE :tag", tag=f"{tag}-%")

    have_contacts = await _scalar(db, "SELECT count(*) FROM contacts WHERE source = :tag", tag=tag)
    if have_contacts < contacts:
        await db.execute(
            text(
                "INSERT INTO contacts (first_name, last_name, email, phone, language, do_not_contact, marketing_opt_out, "
                "legal_basis, source, owner_id, created_at, updated_at) "
                "SELECT f, l, lower(f || '.' || l || '.' || g || '@example.be'), NULL, (ARRAY['en','fr','nl'])[1 + g % 3], "
                "false, false, 'legitimate_interest', :tag, (CAST(:owners AS integer[]))[1 + g % "
                "cardinality(CAST(:owners AS integer[]))], now(), now() "
                "FROM (SELECT g, (CAST(:firsts AS text[]))[1 + g % cardinality(CAST(:firsts AS text[]))] AS f, "
                "(CAST(:lasts AS text[]))[1 + (g / 12) % cardinality(CAST(:lasts AS text[]))] || g AS l FROM "
                "generate_series(CAST(:start AS integer), CAST(:stop AS integer)) AS g) s"
            ),
            {
                "tag": tag,
                "owners": dataset.user_ids,
                "firsts": FIRST_NAMES,
                "lasts": LAST_NAMES,
                "start": have_contacts + 1,
                "stop": contacts,
            },
        )
        await db.execute(
            text(
                "INSERT INTO contact_employments (contact_id, company_id, function) "
                "SELECT c.id, CAST(:first_company AS integer) + (c.id % CAST(:companies AS integer)), 'Director' FROM "
                "contacts c "
                "WHERE c.source = :tag AND NOT EXISTS (SELECT 1 FROM contact_employments e WHERE e.contact_id = c.id)"
            ),
            {"first_company": first_company, "companies": companies, "tag": tag},
        )

    have_deals = await _scalar(db, "SELECT count(*) FROM mandates WHERE code_name_key LIKE :tag", tag=f"{tag}-deal-%")
    if have_deals < deals:
        await db.execute(
            text(
                "INSERT INTO mandates (code_name, code_name_key, client_id, type, sector_id, lead_partner_id, "
                "estimated_ev, "
                "stage, created_at, updated_at, version, conflict_status, target_id) "
                "SELECT 'Project ' || g, CAST(:tag AS text) || '-deal-' || g, CAST(:first_company AS integer) + (g * 7 "
                "% CAST(:companies AS integer)), "
                "(ARRAY['sell_side','buy_side'])[1 + g % 2], :sector, (CAST(:partners AS integer[]))[1 + g % "
                "cardinality(CAST(:partners AS integer[]))], "
                "1000 + g * 3, "
                "(ARRAY['preparation','marketing','due_diligence','spa_negotiation','indicative_offers'])[1 + g % 5], "
                "now() - (g || ' hours')::interval, now(), 1, 'clear', CAST(:first_company AS integer) + ((g * 7 + 1) "
                "% CAST(:companies AS integer)) "
                "FROM generate_series(CAST(:start AS integer), CAST(:stop AS integer)) AS g"
            ),
            {
                "tag": tag,
                "first_company": first_company,
                "companies": companies,
                "sector": sector,
                "partners": partners,
                "start": have_deals + 1,
                "stop": deals,
            },
        )
        await db.execute(
            text(
                "INSERT INTO deal_team_members (mandate_id, user_id, role, added_by, added_at) "
                "SELECT DISTINCT ON (m.id, u.uid) m.id, u.uid, CASE WHEN u.uid = m.lead_partner_id THEN 'lead_partner' "
                "ELSE 'analyst' END, "
                "m.lead_partner_id, now() FROM mandates m "
                "CROSS JOIN LATERAL (SELECT m.lead_partner_id AS uid UNION SELECT (CAST(:staff AS integer[]))[1 + "
                "((m.id * 13 + k) % cardinality(CAST(:staff AS integer[])))] "
                "FROM generate_series(1, CAST(:team AS integer)) AS k) u "
                "WHERE m.code_name_key LIKE :tag "
                "AND NOT EXISTS (SELECT 1 FROM deal_team_members t WHERE t.mandate_id = m.id AND t.user_id = u.uid)"
            ),
            {"staff": staffable, "team": team_size - 1, "tag": f"{tag}-deal-%"},
        )

    if with_tokens:
        for user_id in dataset.user_ids:
            secret = PERSONAL_PREFIX + secrets.token_urlsafe(32)
            await db.execute(
                text(
                    "INSERT INTO api_tokens (user_id, kind, name, prefix, token_hash, created_at) "
                    "VALUES (:user_id, 'personal', :name, :prefix, :hash, now())"
                ),
                {
                    "user_id": user_id,
                    "name": f"{tag} load test",
                    "prefix": secret[:SHOWN_PREFIX_LENGTH],
                    "hash": hashlib.sha256(secret.encode()).hexdigest(),
                },
            )
            dataset.tokens[user_id] = secret
    await db.commit()
    await db.execute(text("ANALYZE"))
    dataset.contacts = await _scalar(db, "SELECT count(*) FROM contacts WHERE source = :tag", tag=tag)
    dataset.companies = await _scalar(
        db, "SELECT count(*) FROM companies WHERE vat_or_registry_number LIKE :tag", tag=f"{tag}-%"
    )
    dataset.deals = await _scalar(db, "SELECT count(*) FROM mandates WHERE code_name_key LIKE :tag", tag=f"{tag}-deal-%")
    return dataset
