"""Parse one strict JSON object without duplicate keys or non-finite values."""

import json


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate key")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise ValueError("JSON contains a non-finite number: " + value)


def parse_json_object(value: str) -> dict[str, object]:
    """Return a strict top-level JSON object."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    try:
        result = json.loads(
            value,
            object_pairs_hook=_object,
            parse_constant=_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("value is not valid JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("JSON value must be an object")
    return result
