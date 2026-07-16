from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.canonical import canonical_digest
from taedri_codegraph.contracts import ProducerRef, SubjectRef, TypedValue, ValueKind
from taedri_codegraph.representations import (
    RepresentationDescriptor,
    RepresentationSeed,
    core_representation_registry,
    materialize_seeds,
)
from taedri_codegraph.storage import GraphStore
from tests.helpers import GOLDEN


class ExtensibleRepresentationStorageTests(unittest.TestCase):
    def test_new_license_scalar_character_and_vector_facets_need_no_ledger_migration(self) -> None:
        analyzer = PythonSyntaxAnalyzer()
        bundle = analyzer.analyze(GOLDEN, package_name="pkg", release="1.0.0")
        entity = next(
            value for value in bundle.entities.values() if value.native_name == "Widget"
        )
        evidence_id = next(iter(bundle.evidence))
        subject = SubjectRef("entity", entity.identity.id)
        registry = core_representation_registry()
        descriptors = (
            RepresentationDescriptor(
                "example.family.license",
                "example.license.spdx",
                "1.0.0",
                "https://example.test/registry",
                ("entity",),
                (ValueKind.KEYWORD,),
                ("exact", "facet", "lexical"),
            ),
            RepresentationDescriptor(
                "example.family.metric",
                "example.metric.support_score",
                "1.0.0",
                "https://example.test/registry",
                ("entity",),
                (ValueKind.INTEGER,),
                ("scalar",),
            ),
            RepresentationDescriptor(
                "example.family.character",
                "example.character.prefix",
                "1.0.0",
                "https://example.test/registry",
                ("entity",),
                (ValueKind.KEYWORD,),
                ("facet",),
            ),
            RepresentationDescriptor(
                "example.family.embedding",
                "example.embedding.contract4",
                "1.0.0",
                "https://example.test/registry",
                ("entity",),
                (ValueKind.DENSE_VECTOR,),
                ("vector",),
            ),
        )
        registry.register_many(descriptors)
        seeds = (
            RepresentationSeed(
                subject,
                item.family_key,
                item.representation_key,
                value,
                evidence_ids=(evidence_id,),
                input_ref=SubjectRef("entity", entity.identity.id),
            )
            for item, value in zip(
                descriptors,
                (
                    TypedValue(ValueKind.KEYWORD, "MIT"),
                    TypedValue(ValueKind.INTEGER, 91),
                    TypedValue(ValueKind.KEYWORD, "W"),
                    TypedValue(
                        ValueKind.DENSE_VECTOR,
                        {"dimensions": 4, "values": [1, "0.25", -1, 0]},
                    ),
                ),
                strict=True,
            )
        )
        materialize_seeds(
            bundle,
            seeds,
            producer=ProducerRef(
                "example.flex-analyzer",
                "1.0.0",
                canonical_digest({"fixture": "typed-flexibility"}),
            ),
            attempt_key="flexibility-v1",
        )

        with tempfile.TemporaryDirectory() as temporary:
            store = GraphStore(Path(temporary) / "graph")
            epoch = store.write_candidate(bundle, analyzer.registry, registry)
            store.publish_epoch(epoch)
            index = store.index()
            rows = index.search_representations(
                representation_key="example.license.spdx", text="MIT"
            )
            self.assertEqual(rows[0]["subject_id"], entity.identity.id)
            with index._connect() as connection:
                facet = connection.execute(
                    "SELECT entity_id FROM facet WHERE representation_key=? AND value=?",
                    ("example.license.spdx", "MIT"),
                ).fetchone()
                scalar = connection.execute(
                    "SELECT integer_value FROM scalar WHERE representation_key=?",
                    ("example.metric.support_score",),
                ).fetchone()
                vector = connection.execute(
                    "SELECT dimensions FROM vector WHERE representation_key=?",
                    ("example.embedding.contract4",),
                ).fetchone()
                lineage_count = connection.execute(
                    "SELECT COUNT(*) FROM lineage WHERE target_id=?",
                    (entity.identity.id,),
                ).fetchone()[0]
            self.assertEqual(facet[0], entity.identity.id)
            self.assertEqual(scalar[0], 91)
            self.assertEqual(vector[0], 4)
            self.assertGreaterEqual(lineage_count, 4)


if __name__ == "__main__":
    unittest.main()
