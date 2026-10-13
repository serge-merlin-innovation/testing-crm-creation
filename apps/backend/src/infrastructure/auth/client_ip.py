from crudauth.utils import get_client_ip
from fastapi import Request

from ..config.settings import settings


def client_ip(request: Request) -> str | None:
    return get_client_ip(request, settings.TRUSTED_PROXY_HOPS) or None
