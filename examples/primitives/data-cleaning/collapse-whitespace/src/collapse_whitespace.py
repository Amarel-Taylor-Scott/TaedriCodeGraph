"""Collapse every run of Unicode whitespace to one ASCII space."""


def collapse_whitespace(value: str) -> str:
    """Return a stripped string with internal whitespace runs collapsed."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return " ".join(value.split())
