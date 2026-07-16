from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.contracts import ProducerRef
from taedri_codegraph.primitive_capsules import (
    CapsuleRole,
    PrimitiveRegistry,
    PrimitiveTreeEntry,
    encode_primitive_pack,
)
from taedri_codegraph.primitives.digestion import FilesystemBlobCache, PrimitiveDigester


class PrimitiveDigestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        registry = PrimitiveRegistry()
        handle = registry.register_handle("acme", "normalize")
        self.source = registry.put_blob(
            b"def normalize(value):\n    return value.strip()\n", "text/x-python"
        )
        contract = registry.put_blob(
            b'{"input":"str","output":"str"}', "application/json"
        )
        verifier = registry.put_blob(b"#!/bin/sh\nexit 0\n", "text/x-shellscript")
        tree = registry.create_tree(
            (
                PrimitiveTreeEntry(
                    "src/normalize.py", CapsuleRole.SOURCE, self.source, "100755"
                ),
                PrimitiveTreeEntry("contract.json", CapsuleRole.CONTRACT, contract),
                PrimitiveTreeEntry(
                    "verify.sh", CapsuleRole.VERIFIER, verifier, "100755"
                ),
            )
        )
        revision = registry.commit(
            primitive=handle,
            tree_id=tree.identity.id,
            contract_digest=contract.digest,
            producer=ProducerRef(
                "taedri.test", "1.0.0", "sha256:" + "1" * 64
            ),
            author="test",
            created_at="2026-07-16T12:00:00Z",
            message="fixture",
        )
        pack = registry.build_pack(
            revision.identity.id, have_digests=(self.source.digest,)
        )
        self.encoded = encode_primitive_pack(pack, registry.payloads_for(pack))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_thin_pack_uses_verified_cache_and_omits_verifier(self) -> None:
        cache = FilesystemBlobCache(self.root / "cache")
        cache.put(self.source, b"def normalize(value):\n    return value.strip()\n")
        receipt = PrimitiveDigester().materialize(
            self.encoded, self.root / "checkout", cache=cache
        )
        self.assertEqual(receipt.cache_hits, 1)
        self.assertIn("verifier", receipt.omitted_roles)
        self.assertEqual(receipt.executable_bits_removed, 1)
        self.assertEqual(
            (self.root / "checkout/src/normalize.py").read_text(),
            "def normalize(value):\n    return value.strip()\n",
        )
        self.assertTrue((self.root / "checkout/contract.json").is_file())
        self.assertFalse((self.root / "checkout/verify.sh").exists())
        self.assertEqual(
            (self.root / "checkout/src/normalize.py").stat().st_mode & 0o111, 0
        )

    def test_missing_thin_pack_cache_blob_fails_before_materialization(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing cached blob"):
            PrimitiveDigester().materialize(
                self.encoded, self.root / "missing", cache=FilesystemBlobCache(self.root / "empty")
            )
        self.assertFalse((self.root / "missing/src/normalize.py").exists())


if __name__ == "__main__":
    unittest.main()
