from typing import Protocol

EU_COUNTRIES = frozenset("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())


class GeoIp(Protocol):
    def country(self, ip: str | None) -> str | None:
        """ISO 3166-1 alpha-2 code, or None when unknown."""
        ...


class UnknownGeoIp:
    def country(self, ip: str | None) -> str | None:
        return None


class StaticGeoIp:
    def __init__(self, countries: dict[str, str] | None = None) -> None:
        self.countries = dict(countries or {})

    def country(self, ip: str | None) -> str | None:
        return self.countries.get(ip or "")


_geoip: GeoIp = UnknownGeoIp()


def get_geoip() -> GeoIp:
    return _geoip


def set_geoip(geoip: GeoIp) -> None:
    global _geoip
    _geoip = geoip
