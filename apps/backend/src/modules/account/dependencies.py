from typing import Annotated

from fastapi import Depends

from .service import AccountService


def get_account_service() -> AccountService:
    return AccountService()


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
