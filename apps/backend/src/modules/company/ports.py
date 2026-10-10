from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


class RegisterUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class RegisterEntry:
    legal_name: str
    address: str | None
    nace_code: str | None
    legal_form: str | None


class EnterpriseRegister(Protocol):
    """The KBO/BCE register. Raises RegisterUnavailableError when it cannot answer."""

    async def lookup(self, enterprise_number: str) -> RegisterEntry | None: ...


@dataclass(frozen=True)
class FiledAccounts:
    year: int
    filed_on: date
    revenue: Decimal | None
    ebitda: Decimal | None
    net_debt: Decimal | None
    fte: Decimal | None


class AnnualAccountsSource(Protocol):
    """Filed annual accounts at the National Bank (NBB), amounts in EUR thousands."""

    async def latest(self, enterprise_number: str, years: int) -> list[FiledAccounts]: ...


class UnconfiguredRegister:
    async def lookup(self, enterprise_number: str) -> RegisterEntry | None:
        raise RegisterUnavailableError("No KBO/BCE adapter is configured")


class UnconfiguredAnnualAccounts:
    async def latest(self, enterprise_number: str, years: int) -> list[FiledAccounts]:
        raise RegisterUnavailableError("No NBB adapter is configured")
