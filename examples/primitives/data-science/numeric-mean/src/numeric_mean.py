"""Compute a finite floating-point arithmetic mean."""

import math


def numeric_mean(values: list[float]) -> float:
    """Return the arithmetic mean using math.fsum."""

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
    return math.fsum(numbers) / len(numbers)
