from dataclasses import dataclass, field

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.email import InMemoryEmailSender, LoggingEmailSender, set_email_sender
from src.interfaces.main import app
from src.modules.picklist.models import PicklistValue
from src.modules.picklist.service import seed_default_picklists
from src.modules.role.permissions import RoleName
from tests.integration.foundation.helpers import login, make_user


@dataclass
class Actor:
    id: int
    email: str
    client: AsyncClient
    headers: dict[str, str]


@dataclass
class World:
    db: AsyncSession
    emails: InMemoryEmailSender
    sector_id: int
    country_id: int
    actors: dict[str, Actor] = field(default_factory=dict)
    clients: list[AsyncClient] = field(default_factory=list)

    async def actor(self, key: str, role: RoleName | None) -> Actor:
        email = f"{key}@firm.be"
        user = await make_user(self.db, email, role)
        session = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.clients.append(session)
        headers = await login(session, email)
        actor = Actor(user["id"], email, session, headers)
        self.actors[key] = actor
        return actor

    async def company(self, name: str, company_type: str = "target") -> int:
        partner = next(iter(self.actors.values()))
        response = await partner.client.post(
            "/api/v1/companies/",
            json={"name": name, "type": company_type, "country_id": self.country_id, "vat_or_registry_number": name},
            headers=partner.headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    async def close(self) -> None:
        set_email_sender(LoggingEmailSender())
        for session in self.clients:
            await session.aclose()


async def build_world(db: AsyncSession) -> World:
    await seed_default_picklists(db)
    sector = PicklistValue(kind="sector", code="tech", label_en="Technology")
    db.add(sector)
    await db.commit()
    country_id = (
        await db.execute(select(PicklistValue.id).where(PicklistValue.kind == "country", PicklistValue.code == "NL"))
    ).scalar_one()
    emails = InMemoryEmailSender()
    set_email_sender(emails)
    return World(db=db, emails=emails, sector_id=sector.id, country_id=country_id)


def mandate_payload(world: World, client_id: int, lead_partner_id: int, **overrides) -> dict:
    payload = {
        "code_name": "Falcon",
        "client_id": client_id,
        "type": "sell_side",
        "sector_id": world.sector_id,
        "lead_partner_id": lead_partner_id,
        "estimated_ev": "25000",
    }
    payload.update(overrides)
    return payload


async def create_mandate(world: World, partner: Actor, client_id: int, **overrides) -> dict:
    response = await partner.client.post(
        "/api/v1/mandates/",
        json=mandate_payload(world, client_id, partner.id, **overrides),
        headers=partner.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def seed_buyers(world: World, lead: Actor, mandate_id: int) -> dict:
    """An approved buyer on the deal, and a second buyer company not yet listed: the matrix context for buyer routes."""
    listed = await world.company("Listed Buyer Capital", "financial_investor")
    spare = await world.company("Spare Buyer Capital", "financial_investor")
    added = await lead.client.post(
        f"/api/v1/mandates/{mandate_id}/buyers",
        json={"items": [{"company_id": listed, "owner_id": lead.id, "rationale": "Fit"}]},
        headers=lead.headers,
    )
    assert added.status_code == 200, added.text
    buyer_id = added.json()["added"][0]
    approved = await lead.client.patch(
        f"/api/v1/mandates/{mandate_id}/buyers/{buyer_id}", json={"approval": "approved"}, headers=lead.headers
    )
    assert approved.status_code == 200, approved.text
    return {"buyer_id": buyer_id, "buyer_company_id": spare, "lead_id": lead.id}
