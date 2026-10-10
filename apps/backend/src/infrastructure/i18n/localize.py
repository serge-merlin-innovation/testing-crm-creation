"""Turns the English text the code writes (errors, notifications, emails) into FR or NL.

Messages are written in English at the call site; `translations.json` maps each English template
({0}, {1} mark the variable parts) to its FR and NL wording. `tests/unit/infrastructure/test_i18n_coverage.py`
fails when a raised message or notification in `src/modules` has no entry, so a new string ships translated.
"""

import json
import re
from functools import cache
from pathlib import Path

from .catalogue import Language

TRANSLATIONS = Path(__file__).parent / "messages" / "translations.json"


@cache
def _table() -> dict[str, dict[str, str]]:
    table: dict[str, dict[str, str]] = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    return table


@cache
def _patterns() -> list[tuple[re.Pattern[str], str]]:
    compiled = []
    for template in _table():
        if "{0}" not in template:
            continue
        pieces = re.split(r"\{(\d)\}", template)
        regex = "".join(re.escape(piece) if index % 2 == 0 else f"(?P<v{piece}>.+?)" for index, piece in enumerate(pieces))
        compiled.append((re.compile(f"^{regex}$", re.DOTALL), template))
    # Longest literal text first, so "{0} {1} not found" never shadows "Picklist value {0} not found".
    compiled.sort(key=lambda item: -len(re.sub(r"\{\d\}", "", item[1])))
    return compiled


def resolve_language(value: str | None) -> Language:
    for part in (value or "").replace(";", ",").split(","):
        code = part.strip().lower()[:2]
        if code in ("en", "fr", "nl"):
            return Language(code)
    return Language.EN


def localize(text: str, language: str | None) -> str:
    chosen = resolve_language(language)
    if chosen == Language.EN or not text:
        return text
    exact = _table().get(text)
    if exact is not None:
        return exact.get(chosen.value) or text
    for pattern, template in _patterns():
        match = pattern.match(text)
        if match:
            translated = _table()[template].get(chosen.value)
            if not translated:
                return text
            values = {f"{{{name[1:]}}}": value for name, value in match.groupdict().items()}
            return re.sub(r"\{\d\}", lambda placeholder: values.get(placeholder.group(0), placeholder.group(0)), translated)
    return text


def known_templates() -> set[str]:
    return set(_table())
