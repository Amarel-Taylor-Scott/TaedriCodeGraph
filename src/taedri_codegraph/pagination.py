"""Opaque, tamper-evident cursors bound to immutable query scope."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Mapping

from .canonical import canonical_json_bytes, sha256_digest, to_primitive


class CursorError(ValueError):
    """Raised when a cursor is malformed, modified, stale, or out of scope."""


_MAX_CURSOR_BYTES = 8192
_MAX_OFFSET = 1000


def encode_cursor(scope: Mapping[str, Any], offset: int) -> str:
    if not 1 <= offset <= _MAX_OFFSET:
        raise CursorError("cursor offset must be between 1 and 1000")
    primitive_scope = to_primitive(dict(scope))
    if not isinstance(primitive_scope, dict):  # pragma: no cover
        raise CursorError("cursor scope must be an object")
    body = {
        "format_version": "1.0.0",
        "offset": offset,
        "scope": primitive_scope,
    }
    envelope = {"body": body, "checksum": sha256_digest(canonical_json_bytes(body))}
    encoded = base64.urlsafe_b64encode(canonical_json_bytes(envelope)).rstrip(b"=")
    if len(encoded) > _MAX_CURSOR_BYTES:
        raise CursorError("cursor exceeds the encoded size limit")
    return encoded.decode("ascii")


def decode_cursor(value: str, expected_scope: Mapping[str, Any]) -> int:
    if not value or len(value) > _MAX_CURSOR_BYTES:
        raise CursorError("cursor is empty or exceeds the encoded size limit")
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        envelope = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CursorError("cursor encoding is invalid") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"body", "checksum"}:
        raise CursorError("cursor envelope is invalid")
    body = envelope["body"]
    checksum = envelope["checksum"]
    if not isinstance(body, dict) or not isinstance(checksum, str):
        raise CursorError("cursor envelope is invalid")
    if checksum != sha256_digest(canonical_json_bytes(body)):
        raise CursorError("cursor checksum does not match")
    if body.get("format_version") != "1.0.0":
        raise CursorError("cursor version is unsupported")
    offset = body.get("offset")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 1 <= offset <= _MAX_OFFSET:
        raise CursorError("cursor offset is invalid")
    expected = to_primitive(dict(expected_scope))
    if canonical_json_bytes(body.get("scope")) != canonical_json_bytes(expected):
        raise CursorError("cursor does not belong to this query or immutable epoch")
    return offset
