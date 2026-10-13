from typing import Annotated

from fastapi import Depends

from .ports import AnnualAccountsSource, EnterpriseRegister, UnconfiguredAnnualAccounts, UnconfiguredRegister
from .service import CompanyService

_register: EnterpriseRegister = UnconfiguredRegister()
_accounts: AnnualAccountsSource = UnconfiguredAnnualAccounts()


def set_registers(register: EnterpriseRegister | None, accounts: AnnualAccountsSource | None) -> None:
    """Swap the KBO/BCE and NBB adapters; None restores the unconfigured default."""
    global _register, _accounts
    _register = register or UnconfiguredRegister()
    _accounts = accounts or UnconfiguredAnnualAccounts()


def get_enterprise_register() -> EnterpriseRegister:
    return _register


def get_annual_accounts() -> AnnualAccountsSource:
    return _accounts


def get_company_service(
    register: Annotated[EnterpriseRegister, Depends(get_enterprise_register)],
    accounts: Annotated[AnnualAccountsSource, Depends(get_annual_accounts)],
) -> CompanyService:
    return CompanyService(register, accounts)


CompanyServiceDep = Annotated[CompanyService, Depends(get_company_service)]
