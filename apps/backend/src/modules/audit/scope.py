from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import false
from sqlalchemy.ext.asyncio import AsyncSession

# A condition on AuditEntry for this reader, or None when they see every row.
ReadScope = Callable[[AsyncSession, dict[str, Any], Any], Awaitable[Any]]


async def no_rows_yet(db: AsyncSession, user: dict[str, Any], now: Any) -> Any:
    """Until the deal slices register their scope, readers see no row rather than every deal's rows."""
    return false()


_scope: ReadScope = no_rows_yet


def set_audit_scope(scope: ReadScope) -> None:
    global _scope
    _scope = scope


async def readable_rows(db: AsyncSession, user: dict[str, Any], now: Any) -> Any:
    return await _scope(db, user, now)
