"""Parse one finite decimal or scientific-notation string as a number."""

import math
import re


_INTEGER = re.compile(r"^[+-]?[0-9]+$")
_NUMBER = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)


def coerce_finite_number(value: str) -> int | float:
    """Return an integer when exact integer syntax is used, otherwise float."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    text = value.strip()
    if not text:
        raise ValueError("value is empty")
    if not _NUMBER.fullmatch(text):
        raise ValueError("value is not numeric")
    if _INTEGER.fullmatch(text):
        return int(text)
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError("value is not numeric") from exc
    if not math.isfinite(number):
        raise ValueError("value must be finite")
    return number
