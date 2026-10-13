from typing import Annotated

from fastapi import Depends

from .service import BuyerService, InvestorProfileService


def get_buyer_service() -> BuyerService:
    return BuyerService()


BuyerServiceDep = Annotated[BuyerService, Depends(get_buyer_service)]


def get_investor_profile_service() -> InvestorProfileService:
    return InvestorProfileService()


InvestorProfileServiceDep = Annotated[InvestorProfileService, Depends(get_investor_profile_service)]
