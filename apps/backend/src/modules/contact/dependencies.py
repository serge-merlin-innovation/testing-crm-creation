from typing import Annotated

from fastapi import Depends

from .service import ContactService


def get_contact_service() -> ContactService:
    return ContactService()


ContactServiceDep = Annotated[ContactService, Depends(get_contact_service)]
