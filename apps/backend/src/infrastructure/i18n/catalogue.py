import json
from enum import StrEnum
from functools import cache
from pathlib import Path

CATALOGUE_DIRECTORY = Path(__file__).parent / "messages"


class Language(StrEnum):
    EN = "en"
    FR = "fr"
    NL = "nl"


SUPPORTED_LANGUAGES = tuple(Language)
DEFAULT_LANGUAGE = Language.EN


@cache
def catalogue(language: Language) -> dict[str, str]:
    messages: dict[str, str] = json.loads((CATALOGUE_DIRECTORY / f"{language.value}.json").read_text(encoding="utf-8"))
    return messages


def translate(key: str, language: str | None = None, **values: object) -> str:
    try:
        chosen = Language(language) if language else DEFAULT_LANGUAGE
    except ValueError:
        chosen = DEFAULT_LANGUAGE
    template = catalogue(chosen).get(key) or catalogue(DEFAULT_LANGUAGE).get(key) or key
    return template.format(**values)
