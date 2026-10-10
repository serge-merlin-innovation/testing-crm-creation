from dataclasses import dataclass, field

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.main import app
from src.modules.notification.dependencies import get_email_sender
from src.modules.notification.ports import SentEmail
from src.modules.picklist.models import PicklistValue
from src.modules.picklist.service import seed_default_picklists
from src.modules.role.permissions import RoleName
from tests.integration.foundation.helpers import login, make_user


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    async def send(self, email: SentEmail) -> None:
        self.sent.append(email)


@dataclass
class Actor:
    id: int
    email: str
    client: AsyncClient
    headers: dict[str, str]


@dataclass
class World:
    db: AsyncSession
    emails: FakeEmailSender
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
    emails = FakeEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: emails
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
