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


class StaticRegister:
    def __init__(self, entries: dict[str, RegisterEntry]) -> None:
        self.entries = entries

    async def lookup(self, enterprise_number: str) -> RegisterEntry | None:
        return self.entries.get(enterprise_number)


class StaticAnnualAccounts:
    def __init__(self, accounts: dict[str, list[FiledAccounts]]) -> None:
        self.accounts = accounts

    async def latest(self, enterprise_number: str, years: int) -> list[FiledAccounts]:
        if enterprise_number not in self.accounts:
            raise RegisterUnavailableError("No filed accounts for this number")
        return sorted(self.accounts[enterprise_number], key=lambda row: row.year, reverse=True)[:years]
