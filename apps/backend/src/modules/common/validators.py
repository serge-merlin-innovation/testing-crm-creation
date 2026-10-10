from urllib.parse import urlparse


def https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Only https links are accepted")
    return value


def optional_https_url(value: str | None) -> str | None:
    return None if value is None or value == "" else https_url(value)
