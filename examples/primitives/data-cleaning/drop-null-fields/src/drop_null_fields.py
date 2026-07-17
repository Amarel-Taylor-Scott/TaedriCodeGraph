"""Drop top-level record fields whose value is null."""


def drop_null_fields(value: dict[str, object]) -> dict[str, object]:
    """Return a new object without top-level None values."""

    if not isinstance(value, dict):
        raise TypeError("value must be an object")
    if any(not isinstance(key, str) for key in value):
        raise TypeError("object keys must be strings")
    return {key: item for key, item in value.items() if item is not None}
