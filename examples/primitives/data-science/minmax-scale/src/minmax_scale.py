"""Scale one finite numeric vector to the closed interval [0, 1]."""

import math


def minmax_scale(values: list[float]) -> list[float]:
    """Fit and transform one vector using its minimum and maximum."""

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
    lower = min(numbers)
    upper = max(numbers)
    width = upper - lower
    if width == 0.0:
        return [0.0 for _ in numbers]
    return [(value - lower) / width for value in numbers]
