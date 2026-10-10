"""Pure helpers for templates, the funnel and PDF output."""

import re
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal

from fpdf import FPDF

FIELD = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
# The merge fields a template may use (ADM-07). Report-only fields are filled for reports.
MERGE_FIELDS = (
    "salutation",
    "first_name",
    "last_name",
    "contact_name",
    "buyer_name",
    "code_name",
    "stage",
    "date",
    "funnel",
    "timeline",
    "next_steps",
)
FUNNEL_STEPS = ("approached", "nda", "im", "offers", "binding")


def unknown_fields(text: str) -> list[str]:
    return sorted({name for name in FIELD.findall(text) if name not in MERGE_FIELDS})


def render(text: str, values: Mapping[str, str]) -> str:
    return FIELD.sub(lambda match: values.get(match.group(1), ""), text)


def conversion(counts: Iterable[int]) -> list[Decimal | None]:
    """Each step as a share of the step before it; None after an empty step."""
    result: list[Decimal | None] = []
    previous: int | None = None
    for count in counts:
        if previous is None:
            result.append(Decimal("100.0") if count else None)
        elif previous == 0:
            result.append(None)
        else:
            result.append((Decimal(count) * 100 / previous).quantize(Decimal("0.1"), ROUND_HALF_UP))
        previous = count
    return result


def implied_multiple(ev_millions: Decimal, ebitda_thousands: Decimal | None) -> Decimal | None:
    if ebitda_thousands is None or ebitda_thousands <= 0:
        return None
    return (ev_millions * 1000 / ebitda_thousands).quantize(Decimal("0.1"), ROUND_HALF_UP)


def _latin1(text: str) -> str:
    # The core PDF fonts are Latin-1: French and Dutch accents fit, anything else becomes "?".
    return (
        text.replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-").encode("latin-1", "replace").decode("latin-1")
    )


def pdf(title: str, body: str) -> bytes:
    document = FPDF()
    document.set_title(_latin1(title))
    document.add_page()
    document.set_font("Helvetica", "B", 16)
    document.multi_cell(0, 10, _latin1(title))
    document.ln(4)
    document.set_font("Helvetica", size=11)
    for line in body.splitlines() or [""]:
        document.multi_cell(0, 6, _latin1(line) or " ")
    return bytes(document.output())
