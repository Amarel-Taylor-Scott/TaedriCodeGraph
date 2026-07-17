"""Normalize one finite numeric vector to unit Euclidean length."""

import math


def l2_normalize(values: list[int | float]) -> list[float]:
    """Return a unit-L2 vector, or deterministic zeros for a zero vector."""

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
    norm = math.sqrt(math.fsum(value * value for value in numbers))
    if norm == 0.0:
        return [0.0 for _ in numbers]
    return [value / norm for value in numbers]
