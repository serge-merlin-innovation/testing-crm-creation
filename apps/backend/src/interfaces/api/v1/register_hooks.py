from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ....modules.company.dependencies import set_registers
from ....modules.company.ports import FiledAccounts, RegisterEntry, StaticAnnualAccounts, StaticRegister

# Mounted only with the other test hooks: lets e2e tests stand in for the KBO/BCE and NBB.
router = APIRouter(tags=["Test hooks"])


class FakeEntry(BaseModel):
    legal_name: str
    address: str | None = None
    nace_code: str | None = None
    legal_form: str | None = None


class FakeAccounts(BaseModel):
    year: int
    filed_on: date
    revenue: Decimal | None = None
    ebitda: Decimal | None = None
    net_debt: Decimal | None = None
    fte: Decimal | None = None


class FakeRegisters(BaseModel):
    """Keyed by the 10-digit enterprise number. Both empty restores the unconfigured adapters."""

    entries: dict[str, FakeEntry] = Field(default_factory=dict)
    accounts: dict[str, list[FakeAccounts]] = Field(default_factory=dict)


@router.put("/registers", summary="Answer KBO/BCE lookups and NBB imports from fixed data")
async def set_fake_registers(values: FakeRegisters) -> dict[str, int]:
    if not values.entries and not values.accounts:
        set_registers(None, None)
    else:
        set_registers(
            StaticRegister({number: RegisterEntry(**entry.model_dump()) for number, entry in values.entries.items()}),
            StaticAnnualAccounts(
                {number: [FiledAccounts(**row.model_dump()) for row in rows] for number, rows in values.accounts.items()}
            ),
        )
    return {"entries": len(values.entries), "accounts": len(values.accounts)}
