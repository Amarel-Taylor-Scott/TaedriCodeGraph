"""Normalize one human-provided data column name."""

import unicodedata


def normalize_column_name(value: str) -> str:
    """Return a case-folded underscore-delimited Unicode column name."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    result: list[str] = []
    separator_pending = False
    for character in normalized:
        if character.isalnum():
            if separator_pending and result:
                result.append("_")
            result.append(character)
            separator_pending = False
        else:
            separator_pending = True
    name = "".join(result).strip("_")
    if not name:
        raise ValueError("value does not contain a letter or number")
    return name
