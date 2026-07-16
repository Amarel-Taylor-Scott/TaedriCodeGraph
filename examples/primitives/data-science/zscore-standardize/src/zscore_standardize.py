"""Standardize one finite vector with population variance."""

import math


def zscore_standardize(values: list[float]) -> list[float]:
    """Return zero-mean, unit-population-variance z scores."""

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
    mean = math.fsum(numbers) / len(numbers)
    variance = math.fsum((value - mean) ** 2 for value in numbers) / len(numbers)
    if variance == 0.0:
        return [0.0 for _ in numbers]
    deviation = math.sqrt(variance)
    return [(value - mean) / deviation for value in numbers]
