"""Remove Unicode control-category characters from one string."""

import unicodedata


def remove_control_characters(value: str) -> str:
    """Return value without Unicode general category Cc characters."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return "".join(
        character
        for character in value
        if unicodedata.category(character) != "Cc"
    )
