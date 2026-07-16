"""Collision-resistant UCEG sidecar identity."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .canonical import canonical_cbor, to_primitive

_KIND = re.compile(r"^[a-z][a-z0-9_.-]*$")


class IdentityError(ValueError):
    """Raised when an identity is malformed or does not match its stored key."""


def mint_id(kind: str, canonical_key: Any) -> str:
    if not _KIND.fullmatch(kind):
        raise IdentityError(f"invalid UCEG identity kind: {kind!r}")
    digest = hashlib.sha256(canonical_cbor(canonical_key)).digest()
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return f"uceg:v1:{kind}:{encoded}"


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    """An exact ID plus the canonical key that must always be checked behind it."""

    id: str
    kind: str
    canonical_key: Any

    @classmethod
    def create(cls, kind: str, canonical_key: Any) -> "IdentityRecord":
        primitive = to_primitive(canonical_key)
        return cls(mint_id(kind, primitive), kind, primitive)

    def validate(self) -> None:
        expected = mint_id(self.kind, self.canonical_key)
        if self.id != expected:
            raise IdentityError(
                f"identity/key mismatch for {self.id!r}; expected {expected!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "canonical_key": self.canonical_key}
