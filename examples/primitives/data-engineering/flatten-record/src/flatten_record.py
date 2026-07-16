"""Flatten nested JSON objects with explicit collision rejection."""


def flatten_record(request: dict[str, object]) -> dict[str, object]:
    """Flatten request['record'] using request.get('separator', '.')."""

    if not isinstance(request, dict):
        raise TypeError("request must be an object")
    if set(request) - {"record", "separator"}:
        raise ValueError("request contains unknown fields")
    record = request.get("record")
    separator = request.get("separator", ".")
    if not isinstance(record, dict):
        raise TypeError("record must be an object")
    if not isinstance(separator, str) or not separator:
        raise ValueError("separator must be a non-empty string")
    result: dict[str, object] = {}

    def visit(prefix: str, value: object) -> None:
        if isinstance(value, dict) and value:
            for key, nested in value.items():
                if not isinstance(key, str):
                    raise TypeError("record keys must be strings")
                path = key if not prefix else prefix + separator + key
                visit(path, nested)
            return
        if prefix in result:
            raise ValueError("flattened record has a key collision")
        result[prefix] = value

    for key, value in record.items():
        if not isinstance(key, str):
            raise TypeError("record keys must be strings")
        visit(key, value)
    return result
