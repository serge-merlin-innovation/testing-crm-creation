from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import get_email_sender
from ..notification.ports import EmailSender
from .service import OfferService, ProcessService, TemplateService


def get_process_service(sender: Annotated[EmailSender, Depends(get_email_sender)]) -> ProcessService:
    return ProcessService(sender)


def get_offer_service() -> OfferService:
    return OfferService()


def get_template_service() -> TemplateService:
    return TemplateService()


ProcessServiceDep = Annotated[ProcessService, Depends(get_process_service)]
OfferServiceDep = Annotated[OfferService, Depends(get_offer_service)]
TemplateServiceDep = Annotated[TemplateService, Depends(get_template_service)]
