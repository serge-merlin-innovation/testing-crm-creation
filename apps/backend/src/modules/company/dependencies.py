from typing import Annotated

from fastapi import Depends

from .ports import AnnualAccountsSource, EnterpriseRegister, UnconfiguredAnnualAccounts, UnconfiguredRegister
from .service import CompanyService


def get_enterprise_register() -> EnterpriseRegister:
    return UnconfiguredRegister()


def get_annual_accounts() -> AnnualAccountsSource:
    return UnconfiguredAnnualAccounts()


def get_company_service(
    register: Annotated[EnterpriseRegister, Depends(get_enterprise_register)],
    accounts: Annotated[AnnualAccountsSource, Depends(get_annual_accounts)],
) -> CompanyService:
    return CompanyService(register, accounts)


CompanyServiceDep = Annotated[CompanyService, Depends(get_company_service)]
