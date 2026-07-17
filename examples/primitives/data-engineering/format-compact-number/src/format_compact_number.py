"""Serialize one finite Python number to compact JSON number text."""

import json
import math


def format_compact_number(value: int | float) -> str:
    """Return compact JSON number syntax for one finite number."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("value must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("value must be finite")
    return json.dumps(value, allow_nan=False, separators=(",", ":"))
