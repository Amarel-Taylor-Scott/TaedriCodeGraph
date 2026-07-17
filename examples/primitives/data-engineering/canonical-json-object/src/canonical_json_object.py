"""Serialize one JSON-compatible object with stable key order and spacing."""

import json
import math


def _validate_json(value: object) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("value contains a non-finite number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("object keys must be strings")
        for item in value.values():
            _validate_json(item)
        return
    raise ValueError("value contains a non-JSON type")


def canonical_json_object(value: dict[str, object]) -> str:
    """Return compact UTF-8-preserving JSON with recursively sorted keys."""

    if not isinstance(value, dict):
        raise TypeError("value must be an object")
    _validate_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
