"""NFR-04 c1: every label, email and error reaches the user in EN, FR or NL.

Scans the code for every message a user can read (raised errors, HTTP details, notification and
email titles and bodies) and requires an FR and NL entry for each in `translations.json`.
"""

import ast
import json
from pathlib import Path

import pytest

from src.infrastructure.i18n.localize import TRANSLATIONS, known_templates, localize, resolve_language

SOURCE = Path(__file__).parents[3] / "src"
SCANNED = [SOURCE / "modules", SOURCE / "infrastructure" / "auth"]
MESSAGE_CALLS = {"Message", "EmailMessage", "_send", "notify", "_remind", "_task", "_deal_message"}
TEXT_NAMES = {"title", "body", "subject"}
# Stored data or identifiers, never shown as a sentence: role names, document-link labels the
# stage gate matches on, the authenticator issuer and the import source tag.
NOT_MESSAGES = {
    "Director / Manager",
    "Analyst / Associate",
    "Compliance / Back-office",
    "Amended engagement letter",
    "Engagement letter",
    "M&A CRM",
    "Excel import",
}


def template_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts, index = [], 0
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            else:
                parts.append(f"{{{index}}}")
                index += 1
        return "".join(parts)
    return None


def user_facing_messages() -> dict[str, str]:
    found: dict[str, str] = {}
    for root in SCANNED:
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                candidates: list[ast.AST] = []
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    candidates += node.exc.args[:1]
                    candidates += [k.value for k in node.exc.keywords if k.arg in ("detail", "message")]
                    for candidate in list(candidates):
                        if isinstance(candidate, ast.Dict):
                            candidates += [
                                v
                                for k, v in zip(candidate.keys, candidate.values, strict=True)
                                if isinstance(k, ast.Constant) and k.value == "message"
                            ]
                elif isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                    if name in MESSAGE_CALLS:
                        candidates += [k.value for k in node.keywords if k.arg in TEXT_NAMES]
                        candidates += [arg for arg in node.args if isinstance(arg, (ast.Constant, ast.JoinedStr))]
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        # Module constants holding a sentence (INVALID_CREDENTIALS = "...") end up in responses.
                        if getattr(target, "id", "").isupper() and isinstance(node.value, ast.Constant):
                            candidates.append(node.value)
                        names = target.elts if isinstance(target, ast.Tuple) else [target]
                        values = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
                        for name_node, value in zip(names, values, strict=False):
                            if getattr(name_node, "id", None) in TEXT_NAMES:
                                candidates.append(value)
                for candidate in candidates:
                    template = template_of(candidate)
                    # Bare identifiers ("deal_team.added") are event kinds, not prose.
                    if template and " " in template.strip() and template not in NOT_MESSAGES:
                        found[template] = f"{path.relative_to(SOURCE)}:{node.lineno}"
    return found


def test_every_user_facing_message_has_french_and_dutch():
    table = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    missing = {
        message: where
        for message, where in user_facing_messages().items()
        if not (table.get(message, {}).get("fr") and table.get(message, {}).get("nl"))
    }
    assert not missing, "Add FR and NL to translations.json for:\n" + "\n".join(f"{w}: {m!r}" for m, w in missing.items())


def test_translations_keep_their_placeholders():
    table = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    for english, translated in table.items():
        wanted = sorted(set(__import__("re").findall(r"\{\d\}", english)))
        for language in ("fr", "nl"):
            assert sorted(set(__import__("re").findall(r"\{\d\}", translated[language]))) == wanted, (english, language)


@pytest.mark.parametrize(
    ("english", "language", "expected"),
    [
        ("You don't have permission for this action.", "fr", "Vous n'avez pas l'autorisation pour cette action."),
        ("Deal 42 not found", "nl", "Deal 42 niet gevonden"),
        ("Picklist value 7 not found", "fr", "Valeur de liste 7 introuvable"),
        ("Something unknown", "nl", "Something unknown"),
        ("Deal 42 not found", "en", "Deal 42 not found"),
    ],
)
def test_localize(english, language, expected):
    assert localize(english, language) == expected


def test_language_comes_from_a_cookie_or_accept_language_header():
    assert resolve_language("nl-BE,nl;q=0.9,en;q=0.8") == "nl"
    assert resolve_language("de-DE, fr-BE;q=0.5") == "fr"
    assert resolve_language(None) == "en"


def test_the_scan_sees_known_templates():
    assert "Deal {0} not found" in user_facing_messages()
    assert "Deal {0} not found" in known_templates()
