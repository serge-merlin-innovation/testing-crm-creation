def blank(text: str | None) -> bool:
    return text is None or not text.strip()
