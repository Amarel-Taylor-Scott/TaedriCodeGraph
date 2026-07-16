from __future__ import annotations

import unittest

from taedri_codegraph.canonical import canonical_digest
from taedri_codegraph.contracts import (
    EvidenceLevel,
    Modality,
    Polarity,
    ProducerRef,
    RepresentationAssertion,
    RepresentationContent,
    SubjectRef,
    TypedValue,
    ValueKind,
)
from taedri_codegraph.representations import (
    RepresentationDescriptor,
    RepresentationRegistry,
    identifier_blocking_keys,
    lexical_hash_vector,
)


class UniversalRepresentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.producer = ProducerRef("test.labeler", "1.0.0", canonical_digest({"a": 1}))

    def test_content_deduplicates_but_assertion_provenance_does_not(self) -> None:
        first = RepresentationContent.create(
            family_key="example.family.label",
            representation_key="example.label.intent",
            schema_version="1.0.0",
            typed_value=TypedValue(ValueKind.KEYWORD, "parser"),
        )
        second = RepresentationContent.create(
            family_key="example.family.label",
            representation_key="example.label.intent",
            schema_version="1.0.0",
            typed_value=TypedValue(ValueKind.KEYWORD, "parser"),
        )
        self.assertEqual(first.identity.id, second.identity.id)
        asserted = RepresentationAssertion.create(
            snapshot_id="snapshot-1",
            subject=SubjectRef("entity", "entity-1"),
            content_id=first.identity.id,
            modality=Modality.INFERRED,
            polarity=Polarity.POSITIVE,
            producer=self.producer,
            generation_run_id="run-1",
            confidence_ppm=700_000,
            lifecycle=EvidenceLevel.CANDIDATE,
        )
        retried = RepresentationAssertion.create(
            snapshot_id="snapshot-1",
            subject=SubjectRef("entity", "entity-1"),
            content_id=first.identity.id,
            modality=Modality.INFERRED,
            polarity=Polarity.POSITIVE,
            producer=self.producer,
            generation_run_id="run-2",
            confidence_ppm=700_000,
            lifecycle=EvidenceLevel.CANDIDATE,
        )
        self.assertNotEqual(asserted.identity.id, retried.identity.id)

    def test_registry_is_additive_and_typed(self) -> None:
        registry = RepresentationRegistry()
        descriptor = RepresentationDescriptor(
            "example.family.license",
            "example.license.detected",
            "1.0.0",
            "https://example.test/registry",
            ("snapshot", "file"),
            (ValueKind.TEXT,),
            ("lexical", "facet"),
        )
        registry.register(descriptor)
        registry.register(descriptor)
        with self.assertRaises(ValueError):
            registry.register(
                RepresentationDescriptor(
                    "example.family.license",
                    "example.license.detected",
                    "1.0.0",
                    "https://other.test/registry",
                    ("snapshot",),
                    (ValueKind.JSON,),
                    (),
                )
            )

    def test_vector_and_blocking_are_deterministic_search_assists(self) -> None:
        self.assertEqual(lexical_hash_vector("parseAddress"), lexical_hash_vector("parseAddress"))
        self.assertEqual(len(lexical_hash_vector("parseAddress")), 64)
        keys = identifier_blocking_keys("parseAddress", "pkg.parseAddress")
        self.assertIn("exact:parseaddress", keys)
        self.assertTrue(any(item.startswith("tri:") for item in keys))

    def test_typed_values_reject_ambiguous_float_vectors(self) -> None:
        with self.assertRaises(ValueError):
            TypedValue(ValueKind.DENSE_VECTOR, {"dimensions": 2, "values": [0.1, 0.2]})


if __name__ == "__main__":
    unittest.main()
