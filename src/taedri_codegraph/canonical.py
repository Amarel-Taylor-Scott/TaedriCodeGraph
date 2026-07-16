"""Small deterministic encoders used by exact identities and fact shards.

Identity keys intentionally reject floating point values. A confidence score or model
output therefore cannot accidentally become part of exact graph identity.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a value has no stable representation in the selected contract."""


def to_primitive(value: Any) -> Any:
    """Convert records to JSON/CBOR-compatible values without changing semantics."""

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_primitive(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, enum.Enum):
        return to_primitive(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {to_primitive(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_primitive(item) for item in value]
    if isinstance(value, bytes | str | int | float | bool) or value is None:
        return value
    raise CanonicalizationError(f"unsupported canonical value: {type(value).__name__}")


def _head(major: int, argument: int) -> bytes:
    if argument < 0:
        raise CanonicalizationError("CBOR head arguments cannot be negative")
    prefix = major << 5
    if argument < 24:
        return bytes((prefix | argument,))
    if argument <= 0xFF:
        return bytes((prefix | 24, argument))
    if argument <= 0xFFFF:
        return bytes((prefix | 25,)) + argument.to_bytes(2, "big")
    if argument <= 0xFFFFFFFF:
        return bytes((prefix | 26,)) + argument.to_bytes(4, "big")
    if argument <= 0xFFFFFFFFFFFFFFFF:
        return bytes((prefix | 27,)) + argument.to_bytes(8, "big")
    raise CanonicalizationError("integer exceeds the UCEG v1 CBOR range")


def canonical_cbor(value: Any) -> bytes:
    """Encode the deterministic, identity-safe UCEG CBOR v1 subset.

    Maps use deterministic length-first ordering of encoded keys. Indefinite lengths,
    tags, floats, and duplicate canonical keys are intentionally unsupported.
    """

    value = to_primitive(value)
    if value is None:
        return b"\xf6"
    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if isinstance(value, int):
        return _head(0, value) if value >= 0 else _head(1, -1 - value)
    if isinstance(value, float):
        raise CanonicalizationError("floats are forbidden in exact identity keys")
    if isinstance(value, bytes):
        return _head(2, len(value)) + value
    if isinstance(value, str):
        encoded = value.encode("utf-8", errors="strict")
        return _head(3, len(encoded)) + encoded
    if isinstance(value, list):
        return _head(4, len(value)) + b"".join(canonical_cbor(item) for item in value)
    if isinstance(value, dict):
        pairs: list[tuple[bytes, bytes]] = []
        seen: set[bytes] = set()
        for key, item in value.items():
            encoded_key = canonical_cbor(key)
            if encoded_key in seen:
                raise CanonicalizationError("duplicate canonical map key")
            seen.add(encoded_key)
            pairs.append((encoded_key, canonical_cbor(item)))
        pairs.sort(key=lambda pair: (len(pair[0]), pair[0]))
        return _head(5, len(pairs)) + b"".join(key + item for key, item in pairs)
    raise CanonicalizationError(f"unsupported CBOR value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON for persisted human-inspectable records."""

    primitive = to_primitive(value)

    def reject_nonfinite(number: str) -> None:
        raise CanonicalizationError(f"non-finite JSON number: {number}")

    return json.dumps(
        primitive,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=reject_nonfinite,
    ).encode("utf-8")


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256_digest(canonical_cbor(value))
