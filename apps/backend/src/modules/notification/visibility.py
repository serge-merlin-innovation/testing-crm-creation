from collections.abc import Awaitable, Callable, Collection
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

VisibleDeals = Callable[[AsyncSession, dict[str, Any], datetime], Awaitable[Collection[int]]]


async def no_deals_yet(db: AsyncSession, user: dict[str, Any], now: datetime) -> Collection[int]:
    """Until the deal slice registers its wall, no deal notification is listed."""
    return ()


_visible_deals: VisibleDeals = no_deals_yet


def set_visible_deals(visible: VisibleDeals) -> None:
    global _visible_deals
    _visible_deals = visible


async def visible_deal_ids(db: AsyncSession, user: dict[str, Any], now: datetime) -> Collection[int]:
    return await _visible_deals(db, user, now)
