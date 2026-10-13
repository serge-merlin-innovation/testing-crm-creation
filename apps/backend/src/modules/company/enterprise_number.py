import re

_SEPARATORS = re.compile(r"[\s.\-]")


def normalize_enterprise_number(raw: str) -> str | None:
    """Returns the 10 digits of a valid Belgian enterprise number, or None when the checksum fails.

    Accepts `BE0xxx.xxx.xxx`, `0xxx.xxx.xxx` and the bare digits. The last two digits are
    97 minus the first eight modulo 97.
    """
    digits = _SEPARATORS.sub("", raw.strip().upper()).removeprefix("BE")
    if len(digits) == 9:
        digits = "0" + digits
    if not re.fullmatch(r"[01]\d{9}", digits):
        return None
    if 97 - int(digits[:8]) % 97 != int(digits[8:]):
        return None
    return digits


def format_enterprise_number(digits: str) -> str:
    return f"BE{digits[:4]}.{digits[4:7]}.{digits[7:]}"
