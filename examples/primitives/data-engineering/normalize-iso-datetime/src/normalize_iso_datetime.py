"""Normalize one timezone-aware ISO 8601 timestamp to canonical UTC."""

from datetime import datetime, timezone


def normalize_iso_datetime(value: str) -> str:
    """Return a timezone-aware timestamp in UTC with a trailing Z."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("value must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("value must include a UTC offset")
    normalized = parsed.astimezone(timezone.utc)
    timespec = "microseconds" if normalized.microsecond else "seconds"
    return normalized.isoformat(timespec=timespec).removesuffix("+00:00") + "Z"
