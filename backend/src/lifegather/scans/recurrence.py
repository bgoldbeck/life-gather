"""Calendar recurrence with one occurrence through DST folds and gaps."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lifegather.memory.service import MemoryError


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise MemoryError("Choose a valid IANA timezone") from None


def wall_instant(day: date, local_time: str, timezone: ZoneInfo) -> int:
    hour, minute = map(int, local_time.split(":"))
    wall = datetime(day.year, day.month, day.day, hour, minute)
    # A skipped calendar day is possible, not only the usual one-hour spring gap.
    for offset in range(1501):
        candidate = wall + timedelta(minutes=offset)
        aware = candidate.replace(tzinfo=timezone, fold=0)
        stamp = int(aware.timestamp())
        if datetime.fromtimestamp(stamp, timezone).replace(tzinfo=None) == candidate:
            return stamp
    raise MemoryError("Unable to resolve this local schedule time")


def occurrences(
    anchor: int,
    timezone: str,
    cadence: str,
    weekday: int,
    local_time: str,
    *,
    backwards: bool = False,
) -> list[int]:
    tz = zone(timezone)
    today = datetime.fromtimestamp(anchor, UTC).astimezone(tz).date()
    candidates = []
    for delta in range(9):
        day = today + timedelta(days=-delta if backwards else delta)
        if cadence == "weekly" and day.weekday() != weekday:
            continue
        candidates.append(wall_instant(day, local_time, tz))
    return candidates


def next_occurrence(
    after: int, timezone: str, cadence: str, weekday: int, local_time: str
) -> int:
    return min(
        value
        for value in occurrences(after, timezone, cadence, weekday, local_time)
        if value > after
    )


def latest_occurrence(
    now: int, timezone: str, cadence: str, weekday: int, local_time: str
) -> int:
    return max(
        value
        for value in occurrences(
            now, timezone, cadence, weekday, local_time, backwards=True
        )
        if value <= now
    )
