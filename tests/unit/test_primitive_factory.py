from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.contracts import ProducerRef
from taedri_codegraph.intake import CandidateIntakeLedger, CandidateState
from taedri_codegraph.primitive_capsules import CapsuleRole, PrimitiveRegistry
from taedri_codegraph.primitive_factory import PrimitiveFactory


class PrimitiveFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.producer = ProducerRef(
            "taedri.test.primitive-factory",
            "1.0.0",
            sha256_digest(b"factory-fixture"),
        )

    def test_real_source_is_never_executed_and_candidates_are_indexed_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "module.py").write_text(
                "raise RuntimeError('must never execute')\n\n"
                "def normalize(value: str) -> str:\n"
                "    \"\"\"Normalize repeated whitespace.\"\"\"\n"
                "    def pieces():\n"
                "        return value.split()\n"
                "    return ' '.join(pieces())\n\n"
                "class Parser:\n"
                "    async def parse(self, value: str) -> list[str]:\n"
                "        return value.split()\n",
                "utf-8",
            )
            registry = PrimitiveRegistry()
            intake = CandidateIntakeLedger()
            result = PrimitiveFactory().generate(
                root,
                registry=registry,
                intake=intake,
                producer=self.producer,
                package_name="fixture",
                namespace="fixture.candidates",
                source_uri="git+https://example.invalid/fixture",
                source_revision="abc123",
                created_at="2026-07-16T12:00:00Z",
            )
            self.assertEqual(len(result.candidates), 3)
            self.assertEqual(
                {candidate.entity_kind for candidate in result.candidates},
                {"function", "nested_function", "async_method"},
            )
            self.assertTrue(
                all(
                    intake.state(candidate.submission_id or "")
                    is CandidateState.INDEXED_CANDIDATE
                    for candidate in result.candidates
                )
            )
            self.assertEqual(len(intake.events), len(result.candidates) * 4)
            self.assertLess(len(registry.blobs), len(result.candidates) * 6)
            normalize = next(
                item for item in result.candidates if item.qualified_name == "normalize"
            )
            descriptor = json.loads(registry.blobs[normalize.descriptor_digest])
            self.assertEqual(descriptor["embedding_projections"]["status"], "not_attempted")
            self.assertEqual(
                set(descriptor["multiresolution_lsh_inputs"]),
                {"narrow", "medium", "wide"},
            )
            tree = registry.trees[normalize.tree_id]
            self.assertIn(CapsuleRole.DESCRIPTOR, {entry.role for entry in tree.entries})

    def test_factory_identity_is_stable_for_the_same_source_and_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "helper.py").write_text(
                "def helper(value: int = 1) -> int:\n    return value + 1\n", "utf-8"
            )
            kwargs = {
                "producer": self.producer,
                "package_name": "fixture",
                "namespace": "fixture.candidates",
                "source_uri": "git+https://example.invalid/fixture",
                "source_revision": "abc123",
                "created_at": "2026-07-16T12:00:00Z",
            }
            first = PrimitiveFactory().generate(root, registry=PrimitiveRegistry(), **kwargs)
            second = PrimitiveFactory().generate(root, registry=PrimitiveRegistry(), **kwargs)
            self.assertEqual(first.identity.id, second.identity.id)
            self.assertEqual(first.candidates[0].revision_id, second.candidates[0].revision_id)

    def test_syntax_diagnostics_are_retained_without_aborting_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "good.py").write_text("def good():\n    return 1\n", "utf-8")
            (root / "bad.py").write_text("def broken(:\n", "utf-8")
            result = PrimitiveFactory().generate(
                root,
                registry=PrimitiveRegistry(),
                producer=self.producer,
                package_name="fixture",
                namespace="fixture.candidates",
                source_uri="file://fixture",
                created_at="2026-07-16T12:00:00Z",
            )
            self.assertEqual(len(result.candidates), 1)
            self.assertEqual(len(result.diagnostics), 1)
            self.assertEqual(result.diagnostics[0].source_path, "bad.py")


if __name__ == "__main__":
    unittest.main()

