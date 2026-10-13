import hashlib
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx

from ..logging import get_logger

logger = get_logger()

HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/"


class BreachChecker(Protocol):
    async def is_breached(self, password: str) -> bool: ...


async def _http_get(url: str) -> str:
    async with httpx.AsyncClient(timeout=3.0, headers={"Add-Padding": "true"}) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


class HibpRangeChecker:
    """Have I Been Pwned k-anonymity: only the first 5 hex chars of the SHA-1 leave the server."""

    def __init__(self, fetch: Callable[[str], Awaitable[str]] = _http_get) -> None:
        self.fetch = fetch

    async def is_breached(self, password: str) -> bool:
        digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]
        try:
            body = await self.fetch(HIBP_RANGE_URL + prefix)
        except Exception as exc:
            # Fails open: an outage of the breach service must not stop people setting a password.
            logger.warning(f"Breach check unavailable: {exc}")
            return False
        for line in body.splitlines():
            candidate, _, count = line.strip().partition(":")
            if candidate == suffix and count.strip() not in ("", "0"):
                return True
        return False


class StaticBreachList:
    def __init__(self, passwords: set[str]) -> None:
        self.passwords = set(passwords)

    async def is_breached(self, password: str) -> bool:
        return password in self.passwords


_checker: BreachChecker = HibpRangeChecker()


def get_breach_checker() -> BreachChecker:
    return _checker


def set_breach_checker(checker: BreachChecker) -> None:
    global _checker
    _checker = checker
