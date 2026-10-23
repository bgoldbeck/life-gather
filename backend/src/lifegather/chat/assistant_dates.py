"""Check model-selected calendar dates against the user's actual date words."""

import re
from datetime import date, timedelta

MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
MONTH = r"(?:" + "|".join(name[:3] + "(?:" + name[3:] + ")?" for name in MONTHS) + r")"


def stated_date(value: str | None, quote: str, today: date | None) -> str | None:
    if value is None:
        if re.search(r"\b(unknown|clear|remove)\b|don't know|do not know", quote, re.I):
            return None
        raise ValueError("Only clear a date when the user explicitly asks.")
    requested = date.fromisoformat(value)
    if re.search(r"\b(or|maybe|around|between|not)\b", quote, re.I):
        raise ValueError("Ask for one unambiguous calendar date.")
    found = {
        date.fromisoformat(item) for item in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", quote)
    }
    for pattern, reversed_order in [
        (rf"\b({MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", False),
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH})\.?\s+(\d{{4}})\b", True),
    ]:
        for first, second, year in re.findall(pattern, quote, re.I):
            name, day = (second, first) if reversed_order else (first, second)
            month = next(
                i for i, n in enumerate(MONTHS, 1) if n.startswith(name.lower())
            )
            found.add(date(int(year), month, int(day)))
    for relative, offset in [("yesterday", -1), ("today", 0), ("tomorrow", 1)]:
        if re.search(rf"\b{relative}\b", quote, re.I):
            if today is None:
                raise ValueError(
                    "A relative date needs the request's local date and timezone."
                )
            found.add(today + timedelta(days=offset))
    if found != {requested}:
        raise ValueError(
            "The selected date does not match the user's date words; clarify."
        )
    return requested.isoformat()
