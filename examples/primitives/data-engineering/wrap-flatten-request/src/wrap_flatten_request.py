"""Adapt one JSON object to the explicit flatten-record request schema."""


def wrap_flatten_request(value: dict[str, object]) -> dict[str, object]:
    """Return a request that flattens value with the default separator."""

    if not isinstance(value, dict):
        raise TypeError("value must be an object")
    if any(not isinstance(key, str) for key in value):
        raise TypeError("object keys must be strings")
    return {"record": value}
