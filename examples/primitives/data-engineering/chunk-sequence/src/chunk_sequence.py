"""Split a list into bounded contiguous chunks."""


def chunk_sequence(request: dict[str, object]) -> list[list[object]]:
    """Return contiguous request['size'] chunks of request['items']."""

    if not isinstance(request, dict):
        raise TypeError("request must be an object")
    if set(request) != {"items", "size"}:
        raise ValueError("request requires exactly items and size")
    items = request["items"]
    size = request["size"]
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    if isinstance(size, bool) or not isinstance(size, int):
        raise TypeError("size must be an integer")
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[index:index + size] for index in range(0, len(items), size)]
