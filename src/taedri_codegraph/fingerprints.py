"""Deterministic structural and locality-sensitive candidate fingerprints.

These values are retrieval projections. They are never compatibility proofs.
"""

from __future__ import annotations

import ast
import hashlib
import io
import keyword
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass

from .canonical import sha256_digest


@dataclass(frozen=True, slots=True)
class LSHBandFamily:
    """One self-describing LSH table family.

    Presentation labels such as ``narrow`` and ``wide`` never define the
    algorithm.  The exact width, band count, offsets, feature space, and
    version are encoded in every key so incompatible buckets cannot be joined.
    Overlapping tables reduce sensitivity to one arbitrary band boundary.
    """

    profile: str
    width: int
    bands: int
    offsets: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.profile not in {"narrow", "medium", "wide"}:
            raise ValueError("LSH profile must be narrow, medium, or wide")
        if self.width <= 0 or self.bands <= 0:
            raise ValueError("LSH width and band count must be positive")
        if not self.offsets or any(offset < 0 for offset in self.offsets):
            raise ValueError("LSH table offsets must be non-negative")


SIMHASH64_LSH_FAMILIES = (
    LSHBandFamily("narrow", width=8, bands=8, offsets=(0, 4)),
    LSHBandFamily("medium", width=16, bands=4, offsets=(0, 8)),
    LSHBandFamily("wide", width=32, bands=2, offsets=(0, 16)),
)

MINHASH16_LSH_FAMILIES = (
    LSHBandFamily("narrow", width=2, bands=8, offsets=(0, 1)),
    LSHBandFamily("medium", width=4, bands=4, offsets=(0, 2)),
    LSHBandFamily("wide", width=8, bands=2, offsets=(0, 4)),
)


def ast_sha256(node: ast.AST) -> str:
    normalized = ast.dump(node, annotate_fields=True, include_attributes=False)
    return sha256_digest(normalized.encode("utf-8"))


def normalized_python_tokens(source: str) -> tuple[str, ...]:
    """Normalize trivia, identifiers, and literal values for clone nomination."""

    result: list[str] = []
    stream = io.StringIO(source).readline
    try:
        tokens = tokenize.generate_tokens(stream)
        for token in tokens:
            if token.type in {
                tokenize.ENCODING,
                tokenize.ENDMARKER,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.NEWLINE,
                tokenize.NL,
                tokenize.COMMENT,
            }:
                continue
            text = token.string
            if token.type == tokenize.NAME and not keyword.iskeyword(text):
                text = "<id>"
            elif token.type == tokenize.STRING:
                text = "<str>"
            elif token.type == tokenize.NUMBER:
                text = "<num>"
            result.append(f"{token.type}:{text}")
    except (IndentationError, tokenize.TokenError):
        return ()
    return tuple(result)


def simhash64(features: Iterable[str]) -> int:
    vector = [0] * 64
    found = False
    for feature in features:
        found = True
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for bit in range(64):
            vector[bit] += 1 if value & (1 << bit) else -1
    if not found:
        return 0
    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return result


def token_shingles(tokens: Iterable[str], width: int = 3) -> tuple[str, ...]:
    sequence = tuple(tokens)
    if width <= 0:
        raise ValueError("shingle width must be positive")
    if not sequence:
        return ()
    if len(sequence) < width:
        return ("\x1f".join(sequence),)
    return tuple(
        "\x1f".join(sequence[index : index + width])
        for index in range(len(sequence) - width + 1)
    )


def minhash_signature(features: Iterable[str], permutations: int = 16) -> tuple[int, ...]:
    if permutations <= 0:
        raise ValueError("permutations must be positive")
    unique = tuple(sorted(set(features)))
    if not unique:
        return tuple(0 for _ in range(permutations))
    maxima = (1 << 64) - 1
    signature: list[int] = []
    for index in range(permutations):
        salt = index.to_bytes(4, "big")
        signature.append(
            min(
                int.from_bytes(
                    hashlib.blake2b(
                        feature.encode("utf-8"), key=salt, digest_size=8
                    ).digest(),
                    "big",
                )
                for feature in unique
            )
        )
    return tuple(value & maxima for value in signature)


def hamming_distance64(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def minhash_similarity(left: Iterable[int], right: Iterable[int]) -> float:
    left_tuple = tuple(left)
    right_tuple = tuple(right)
    if len(left_tuple) != len(right_tuple) or not left_tuple:
        raise ValueError("MinHash signatures must have the same non-zero length")
    return sum(a == b for a, b in zip(left_tuple, right_tuple, strict=True)) / len(
        left_tuple
    )


def _circular_slice(
    sequence: tuple[object, ...], start: int, width: int
) -> tuple[object, ...]:
    if not sequence:
        raise ValueError("cannot band an empty sequence")
    return tuple(sequence[(start + offset) % len(sequence)] for offset in range(width))


def simhash64_lsh_keys(
    value: int | str,
    families: Iterable[LSHBandFamily] = SIMHASH64_LSH_FAMILIES,
) -> tuple[str, ...]:
    """Return overlapping narrow/medium/wide SimHash candidate keys.

    These keys nominate candidates only.  Exact Hamming distance and downstream
    verification remain authoritative.
    """

    if isinstance(value, str):
        if len(value) != 16:
            raise ValueError("SimHash hexadecimal value must contain 16 characters")
        try:
            numeric = int(value, 16)
        except ValueError as exc:
            raise ValueError("SimHash value must be hexadecimal") from exc
    else:
        numeric = value
    if not 0 <= numeric < (1 << 64):
        raise ValueError("SimHash value must fit in 64 bits")
    bits = tuple(f"{numeric:064b}")
    keys: list[str] = []
    for family in families:
        if family.width * family.bands != 64:
            raise ValueError("SimHash LSH family must cover exactly 64 bits per table")
        for table, offset in enumerate(family.offsets):
            for band in range(family.bands):
                start = (offset + band * family.width) % 64
                band_bits = "".join(_circular_slice(bits, start, family.width))
                hexadecimal_width = (family.width + 3) // 4
                encoded = f"{int(band_bits, 2):0{hexadecimal_width}x}"
                keys.append(
                    "lsh:v1:simhash64:"
                    f"{family.profile}:w{family.width}:t{table}:o{offset}:b{band}:{encoded}"
                )
    return tuple(keys)


def minhash16_lsh_keys(
    signature: Iterable[int | str],
    families: Iterable[LSHBandFamily] = MINHASH16_LSH_FAMILIES,
) -> tuple[str, ...]:
    """Return overlapping narrow/medium/wide MinHash candidate keys."""

    raw_values = tuple(signature)
    values: tuple[int, ...]
    try:
        values = tuple(
            int(value, 16) if isinstance(value, str) and len(value) == 16 else value
            for value in raw_values
        )
    except ValueError as exc:
        raise ValueError(
            "MinHash16 signature values must be unsigned integers or 16-character hex strings"
        ) from exc
    if len(values) != 16 or any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value < (1 << 64)
        for value in values
    ):
        raise ValueError("MinHash16 signature must contain sixteen unsigned 64-bit integers")
    keys: list[str] = []
    for family in families:
        if family.width * family.bands != 16:
            raise ValueError("MinHash LSH family must cover exactly 16 rows per table")
        for table, offset in enumerate(family.offsets):
            for band in range(family.bands):
                start = (offset + band * family.width) % 16
                band_values = _circular_slice(values, start, family.width)
                encoded = hashlib.sha256(
                    b"".join(value.to_bytes(8, "big") for value in band_values)
                ).hexdigest()[:16]
                keys.append(
                    "lsh:v1:minhash16:"
                    f"{family.profile}:r{family.width}:t{table}:o{offset}:b{band}:{encoded}"
                )
    return tuple(keys)


def lsh_key_profile(key: str) -> tuple[str, str] | None:
    """Return ``(algorithm, profile)`` for a versioned LSH key."""

    parts = key.split(":")
    if len(parts) == 9 and parts[0:2] == ["lsh", "v1"]:
        return parts[2], parts[3]
    return None
