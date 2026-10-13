"""API versions and their support window (NFR-05).

A breaking change ships as a new version under /api/vN. The old version stays mounted until its
sunset, which must be at least six months after the newer version is released.
`tests/unit/interfaces/api/test_public_api_contract.py` enforces both.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

MINIMUM_SUPPORT_MONTHS = 6


@dataclass(frozen=True)
class ApiVersion:
    name: str
    released: date
    # Set when a newer version replaces this one; the date the newer version shipped.
    deprecated: date | None = None
    sunset: date | None = None

    @property
    def prefix(self) -> str:
        return f"/api/{self.name}"

    def describe(self) -> dict[str, Any]:
        return {
            "version": self.name,
            "released": self.released.isoformat(),
            "deprecated": self.deprecated.isoformat() if self.deprecated else None,
            "sunset": self.sunset.isoformat() if self.sunset else None,
        }


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    for candidate in (day.day, 30, 29, 28):
        try:
            return day.replace(year=year, month=month, day=candidate)
        except ValueError:
            continue
    raise ValueError(day)


API_VERSIONS: tuple[ApiVersion, ...] = (ApiVersion(name="v1", released=date(2026, 10, 10)),)


def version_for(path: str) -> ApiVersion | None:
    return next((version for version in API_VERSIONS if path.startswith(version.prefix + "/")), None)
