from __future__ import annotations

import unittest

from taedri_codegraph.canonical import CanonicalizationError, canonical_cbor
from taedri_codegraph.identity import IdentityError, IdentityRecord, mint_id


class CanonicalIdentityTests(unittest.TestCase):
    def test_mapping_order_does_not_change_identity(self) -> None:
        left = mint_id("test", {"alpha": 1, "beta": [True, None]})
        right = mint_id("test", {"beta": [True, None], "alpha": 1})
        self.assertEqual(left, right)

    def test_full_key_is_checked_behind_digest(self) -> None:
        record = IdentityRecord.create("entity", {"name": "value"})
        corrupt = IdentityRecord(record.id, record.kind, {"name": "other"})
        with self.assertRaises(IdentityError):
            corrupt.validate()

    def test_floats_are_forbidden_in_exact_keys(self) -> None:
        with self.assertRaises(CanonicalizationError):
            mint_id("score", {"confidence": 0.5})

    def test_native_unicode_is_not_silently_rewritten(self) -> None:
        composed = mint_id("name", {"native": "é"})
        decomposed = mint_id("name", {"native": "e\u0301"})
        self.assertNotEqual(composed, decomposed)

    def test_deterministic_cbor_vector(self) -> None:
        self.assertEqual(
            canonical_cbor({"a": 1, "bb": [False, None]}).hex(),
            "a261610162626282f4f6",
        )


if __name__ == "__main__":
    unittest.main()
