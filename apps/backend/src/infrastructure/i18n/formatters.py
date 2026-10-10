from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

BELGIAN_TIME_ZONE = ZoneInfo("Europe/Brussels")


def format_date(value: date) -> str:
    if isinstance(value, datetime):
        value = value.astimezone(BELGIAN_TIME_ZONE) if value.tzinfo else value
    return value.strftime("%d/%m/%Y")


def format_datetime(value: datetime) -> str:
    local = value.astimezone(BELGIAN_TIME_ZONE) if value.tzinfo else value
    return local.strftime("%d/%m/%Y %H:%M")


def format_number(value: int | float | Decimal, language: str = "en", decimals: int = 2) -> str:
    """FR and NL use the Belgian 1.234,56; EN keeps 1,234.56."""
    rendered = f"{Decimal(str(value)):,.{decimals}f}"
    if language in ("fr", "nl"):
        return rendered.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    return rendered
