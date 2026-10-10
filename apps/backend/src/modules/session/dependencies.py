from typing import Annotated

from fastapi import Depends

from ...infrastructure.auth.setup import session_transport
from .service import SessionService


def get_session_service() -> SessionService:
    return SessionService(session_transport.clocked)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
