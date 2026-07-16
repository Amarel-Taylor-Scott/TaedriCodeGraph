from __future__ import annotations

import ast
import unittest

from taedri_codegraph.fingerprints import (
    ast_sha256,
    hamming_distance64,
    lsh_key_profile,
    minhash16_lsh_keys,
    minhash_signature,
    minhash_similarity,
    normalized_python_tokens,
    simhash64,
    simhash64_lsh_keys,
    token_shingles,
)


class FingerprintTests(unittest.TestCase):
    def test_ast_digest_ignores_formatting(self) -> None:
        left = ast.parse("def f(x):\n return x + 1\n")
        right = ast.parse("def f(x):\n    return (x+1)\n")
        self.assertEqual(ast_sha256(left), ast_sha256(right))

    def test_normalized_tokens_are_alpha_rename_invariant(self) -> None:
        left = normalized_python_tokens("def add(value): return value + 1")
        right = normalized_python_tokens("def addend(number): return number + 1")
        self.assertEqual(left, right)
        self.assertEqual(simhash64(left), simhash64(right))

    def test_operator_change_affects_candidate_fingerprint(self) -> None:
        left = simhash64(normalized_python_tokens("def f(x): return x + 1"))
        right = simhash64(normalized_python_tokens("def f(x): return x - 1"))
        self.assertGreater(hamming_distance64(left, right), 0)

    def test_minhash_is_deterministic_and_bounded(self) -> None:
        shingles = token_shingles(("a", "b", "c", "d"))
        first = minhash_signature(shingles, permutations=16)
        second = minhash_signature(reversed(shingles), permutations=16)
        self.assertEqual(first, second)
        self.assertEqual(minhash_similarity(first, second), 1.0)

    def test_empty_minhash_does_not_claim_similarity_without_comparison(self) -> None:
        signature = minhash_signature((), permutations=4)
        self.assertEqual(signature, (0, 0, 0, 0))

    def test_multiresolution_lsh_keys_are_self_describing(self) -> None:
        simhash_keys = simhash64_lsh_keys("0123456789abcdef")
        minhash_keys = minhash16_lsh_keys(range(16))
        self.assertEqual(len(simhash_keys), 28)
        self.assertEqual(len(minhash_keys), 28)
        self.assertEqual(
            {lsh_key_profile(key) for key in simhash_keys},
            {
                ("simhash64", "narrow"),
                ("simhash64", "medium"),
                ("simhash64", "wide"),
            },
        )
        self.assertEqual(
            {lsh_key_profile(key) for key in minhash_keys},
            {
                ("minhash16", "narrow"),
                ("minhash16", "medium"),
                ("minhash16", "wide"),
            },
        )

    def test_narrow_family_protects_recall_when_medium_bands_all_change(self) -> None:
        left = 0
        right = sum(1 << bit for bit in (0, 16, 32, 48))
        shared = set(simhash64_lsh_keys(left)) & set(simhash64_lsh_keys(right))
        profiles = {lsh_key_profile(key) for key in shared}
        self.assertIn(("simhash64", "narrow"), profiles)
        self.assertNotIn(("simhash64", "medium"), profiles)


if __name__ == "__main__":
    unittest.main()
