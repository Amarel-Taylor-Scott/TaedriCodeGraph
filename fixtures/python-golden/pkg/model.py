"""Binding, object-model, and relation fixtures."""

import math as maths
from collections.abc import Iterable

MODULE_VALUE: int = 3


def helper(value: int) -> int:
    """Add the module adjustment to one value."""

    return value + MODULE_VALUE


def default_lambda(factory=lambda value: value + 1):
    return factory(MODULE_VALUE)


class Widget:
    """A deliberately small stateful example."""

    category = "golden"

    def __init__(self, name: str):
        self.name = name

    def scale(
        self,
        values: Iterable[int],
        *,
        factor: int = 2,
    ) -> list[int]:
        total = 0
        for item in values:
            total += helper(item)
        try:
            result = [total * factor for total in values]
        except TypeError as error:
            raise ValueError(str(error)) from error
        return result

    async def fetch(self, url: str):
        return await client.get(url)


def binding_forms(items):
    first, *remaining = items
    squares = {item: item * item for item in remaining}
    with open("fixture.txt") as handle:
        text = handle.read()
    if first > 0 and (normalized := maths.floor(first)):
        return normalized, squares, text
    return None


def pattern_capture(payload):
    match payload:
        case {"value": captured, **rest}:
            return captured, rest
        case _:
            return None
