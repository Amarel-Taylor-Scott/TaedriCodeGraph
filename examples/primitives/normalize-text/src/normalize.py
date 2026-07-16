"""Small, dependency-free text normalization primitive."""


def normalize_text(value: str) -> str:
    """Strip leading and trailing Unicode whitespace from a string."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return value.strip()
