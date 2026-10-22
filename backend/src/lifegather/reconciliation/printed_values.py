"""Deterministic readings of amounts, currencies and dates printed in source text.

These checks ground AI suggestions and reviewed purchase details in the exact
characters of a receipt. They never calculate, convert or guess: a value is
supported only when it is printed in the quoted passage, and every alternative
reading is returned so that ambiguity can be shown instead of resolved silently.
"""

import re
from dataclasses import dataclass
from datetime import date

# Longest markers first so "US$" is not read as a bare "$".
MARKERS: dict[str, frozenset[str]] = {
    "US$": frozenset({"USD"}),
    "CA$": frozenset({"CAD"}),
    "AU$": frozenset({"AUD"}),
    "C$": frozenset({"CAD"}),
    "A$": frozenset({"AUD"}),
    "$": frozenset({"USD", "CAD", "AUD"}),
    "€": frozenset({"EUR"}),
    "£": frozenset({"GBP"}),
    "¥": frozenset({"JPY"}),
    "円": frozenset({"JPY"}),
    "USD": frozenset({"USD"}),
    "EUR": frozenset({"EUR"}),
    "GBP": frozenset({"GBP"}),
    "CAD": frozenset({"CAD"}),
    "AUD": frozenset({"AUD"}),
    "JPY": frozenset({"JPY"}),
}
# Symbols shared by currencies outside the supported set or by several of them.
AMBIGUOUS_MARKERS = {
    "$": "A bare $ can mean USD, CAD or AUD",
    "¥": "¥ is also used for Chinese yuan",
}
MARKER = re.compile(
    r"US\$|CA\$|AU\$|C\$|A\$|\$|€|£|¥|円|(?<![A-Za-z])(?:USD|EUR|GBP|CAD|AUD|JPY)(?![A-Za-z])",
    re.I,
)
NUMBER = re.compile(r"(?<![\w.,])\d(?:[\d.,]*\d)?(?![\w]|[.,]\d)")
MONTHS = {
    name: index + 1
    for index, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for name in names
}
MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
ISO_DATE = re.compile(r"(?<![\d/.-])(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?![\d/.-])")
NUMERIC_DATE = re.compile(
    r"(?<![\d/.-])(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})(?![\d/.-])"
)
DAY_MONTH = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH})\.?,?\s+(\d{{4}})\b", re.I
)
MONTH_DAY = re.compile(
    rf"\b({MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I
)
NOT_PURCHASE = re.compile(
    r"\b(?:deliver\w*|ship\w*|dispatch\w*|arriv\w*|return\w*|due|expir\w*|"
    r"warranty|valid\w*|refund\w*|estimated)\b",
    re.I,
)


@dataclass(frozen=True)
class PrintedAmount:
    text: str
    values: frozenset[str]
    currencies: frozenset[str]
    marker: str | None


@dataclass(frozen=True)
class PrintedDate:
    text: str
    readings: frozenset[str]


def _marker(text: str, start: int, end: int) -> str | None:
    """A currency marker touching the number, allowing one space between them."""
    before = list(MARKER.finditer(text, max(0, start - 4), start))
    if before and before[-1].end() >= start - 1:
        return before[-1].group(0)
    gap = 1 if text[end : end + 1] == " " else 0
    after = MARKER.match(text, end + gap)
    return after.group(0) if after else None


def printed_amounts(text: str) -> list[PrintedAmount]:
    """Every money-shaped number with its possible exact decimal readings.

    Decimal amounts read as written (``1,299.00`` and ``1.299,00`` both read as
    ``1299.00``). Whole numbers count only beside a currency marker, so a
    quantity, model number or date part never grounds a price.
    """
    found = []
    for match in NUMBER.finditer(text):
        token = match.group(0)
        marker = _marker(text, match.start(), match.end())
        values: set[str] = set()
        if decimal := re.fullmatch(r"(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})", token):
            values.add(decimal[1].replace(",", "") + "." + decimal[2])
        elif decimal := re.fullmatch(r"(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})", token):
            values.add(decimal[1].replace(".", "") + "." + decimal[2])
        elif marker and re.fullmatch(r"\d+|\d{1,3}(?:[,.]\d{3})+", token):
            whole = re.sub(r"[,.]", "", token)
            values.update({whole, whole + ".00"})
        if not values:
            continue
        values = {re.sub(r"^0+(?=\d)", "", value) for value in values}
        found.append(
            PrintedAmount(
                text=token,
                values=frozenset(values),
                currencies=MARKERS[_canonical(marker)] if marker else frozenset(),
                marker=_canonical(marker) if marker else None,
            )
        )
    return found


def _canonical(marker: str | None) -> str:
    value = (marker or "").upper()
    return value if value in MARKERS else (marker or "")


def printed_markers(text: str) -> list[str]:
    return [_canonical(m.group(0)) for m in MARKER.finditer(text)]


def _real(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def printed_dates(text: str) -> list[PrintedDate]:
    """Every printed calendar date with all of its valid readings.

    ``03/04/2026`` yields both 2026-03-04 and 2026-04-03; a caller must show the
    ambiguity rather than choose a locale.
    """
    found: list[tuple[int, PrintedDate]] = []
    for m in ISO_DATE.finditer(text):
        reading = _real(int(m[1]), int(m[2]), int(m[3]))
        if reading:
            found.append((m.start(), PrintedDate(m[0], frozenset({reading}))))
    for m in NUMERIC_DATE.finditer(text):
        year = int(m[4]) + (2000 if len(m[4]) == 2 else 0)
        readings = {
            r
            for r in (
                _real(year, int(m[1]), int(m[3])),
                _real(year, int(m[3]), int(m[1])),
            )
            if r
        }
        if readings:
            found.append((m.start(), PrintedDate(m[0], frozenset(readings))))
    for m in DAY_MONTH.finditer(text):
        reading = _real(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
        if reading:
            found.append((m.start(), PrintedDate(m[0], frozenset({reading}))))
    for m in MONTH_DAY.finditer(text):
        reading = _real(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
        if reading:
            found.append((m.start(), PrintedDate(m[0], frozenset({reading}))))
    return [value for _, value in sorted(found, key=lambda item: item[0])]


def money_problem(quote: str, line_total: str, currency: str) -> str | None:
    """Why a reviewed total is not supported by its passage, or None if it is."""
    amounts = [a for a in printed_amounts(quote) if line_total in a.values]
    if not amounts:
        return "The line total must be printed in the quoted passage"
    if currency == "JPY" and "." in line_total:
        return "JPY uses whole yen"
    specific = {
        c for m in printed_markers(quote) if len(MARKERS[m]) == 1 for c in MARKERS[m]
    }
    if len(specific) > 1:
        return "The passage prints more than one currency; quote only this item's line"
    marked = {c for a in amounts for c in a.currencies}
    allowed = specific or marked
    if allowed and currency not in allowed:
        return "The chosen currency conflicts with the currency printed in the passage"
    return None


def date_problem(quote: str, purchase_date: str) -> str | None:
    if not any(purchase_date in d.readings for d in printed_dates(quote)):
        return "The purchase date must be a reading of a date printed in the passage"
    return None
