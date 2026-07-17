"""Apply Unicode NFKC compatibility normalization to one string."""

import unicodedata


def normalize_unicode_nfkc(value: str) -> str:
    """Return the Unicode NFKC normalization of value."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return unicodedata.normalize("NFKC", value)
