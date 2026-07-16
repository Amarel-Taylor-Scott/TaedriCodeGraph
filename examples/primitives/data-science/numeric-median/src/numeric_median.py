"""Compute the conventional median of finite numeric values."""

import math


def numeric_median(values: list[float]) -> float:
    """Return the middle value or mean of the two middle values."""

    if not isinstance(values, list):
        raise TypeError("values must be a list")
    if not values:
        raise ValueError("values cannot be empty")
    numbers: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("values must contain numbers")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("values must be finite")
        numbers.append(number)
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return math.fsum((ordered[middle - 1], ordered[middle])) / 2.0
