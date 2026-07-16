"""Unicode-aware case folding primitive."""


def casefold_text(value: str) -> str:
    """Return the Unicode default case-folded form of one string."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return value.casefold()
