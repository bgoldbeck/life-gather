from datetime import date

import pytest
from pydantic import ValidationError

from lifegather.chat.assistant_dates import stated_date
from lifegather.chat.service import TurnInput, request_key
from lifegather.memory.service import fingerprint


@pytest.mark.parametrize(
    "quote, expected",
    [
        ("2026-11-03", "2026-11-03"),
        ("November 3, 2026", "2026-11-03"),
        ("3 November 2026", "2026-11-03"),
        ("today", "2026-10-22"),
        ("yesterday", "2026-10-21"),
        ("tomorrow", "2026-10-23"),
        ("date unknown", None),
    ],
)
def test_date_is_grounded_in_unambiguous_user_words(
    quote: str, expected: str | None
) -> None:
    assert stated_date(expected, quote, date(2026, 10, 22)) == expected


@pytest.mark.parametrize(
    "value, quote, anchor",
    [
        ("2026-10-22", "today", None),
        ("2026-10-23", "today", date(2026, 10, 22)),
        ("2026-11-04", "November 3, 2026", None),
        ("2026-02-30", "2026-02-30", None),
        ("2026-11-03", "November 3 or 4, 2026", None),
        (None, "today", date(2026, 10, 22)),
    ],
)
def test_unknown_context_invented_or_ambiguous_dates_are_refused(
    value: str | None,
    quote: str,
    anchor: date | None,
) -> None:
    with pytest.raises(ValueError):
        stated_date(value, quote, anchor)


def test_timezone_is_validated_and_absence_preserves_old_request_fingerprint() -> None:
    data = TurnInput(
        request_id="timezone",
        mode="assistant",
        text="Log oil change",
        credential_id="synthetic-key",
        model="fixture-model",
    )
    legacy = data.model_dump(
        exclude={
            "source_id",
            "photo_id",
            "document_id",
            "scan",
            "context",
            "research",
            "timezone",
        }
    )
    assert request_key("conversation", data) == fingerprint(["conversation", legacy])
    zoned = data.model_copy(update={"timezone": "America/Los_Angeles"})
    assert request_key("conversation", zoned) != request_key("conversation", data)
    with pytest.raises(ValidationError):
        TurnInput.model_validate({**data.model_dump(), "timezone": "Invented/Timezone"})
