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

from .canonical import sha256_digest


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
