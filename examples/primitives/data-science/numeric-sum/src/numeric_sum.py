"""Accurately sum one non-empty finite numeric vector."""

import math


def numeric_sum(values: list[int | float]) -> float:
    """Return math.fsum over a validated finite numeric list."""

    if not isinstance(values, list):
        raise TypeError("values must be a list")
    if not values:
        raise ValueError("values cannot be empty")
    numbers: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("values must contain numbers")
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError("values must be finite") from exc
        if not math.isfinite(number):
            raise ValueError("values must be finite")
        numbers.append(number)
    return math.fsum(numbers)
