"""Remove duplicate finite JSON values while preserving first occurrence."""

import json


def stable_deduplicate(values: list[object]) -> list[object]:
    """Return first occurrences using canonical JSON equality."""

    if not isinstance(values, list):
        raise TypeError("values must be a list")
    seen: set[str] = set()
    result: list[object] = []
    for value in values:
        try:
            marker = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise TypeError("items must be finite JSON values") from exc
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result
