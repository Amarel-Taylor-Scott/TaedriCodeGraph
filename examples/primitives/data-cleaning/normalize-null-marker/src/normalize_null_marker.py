"""Normalize common textual missing-value markers to JSON null."""


_NULL_MARKERS = frozenset(("", "na", "n/a", "null", "none"))


def normalize_null_marker(value: str) -> str | None:
    """Return None for a fixed missing-value marker, otherwise value."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    if value.strip().casefold() in _NULL_MARKERS:
        return None
    return value
