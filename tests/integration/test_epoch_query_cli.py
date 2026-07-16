from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.cli import main
from taedri_codegraph.storage import EpochValidationError, GraphStore

from tests.helpers import GOLDEN


class EpochQueryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = GraphStore(Path(self.temporary.name) / "store")
        self.analyzer = PythonSyntaxAnalyzer()
        self.bundle = self.analyzer.analyze(GOLDEN, package_name="pkg", release="1.0.0")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_candidate_is_not_visible_until_atomic_publish(self) -> None:
        epoch = self.store.write_candidate(self.bundle, self.analyzer.registry)
        self.assertIn(epoch, self.store.list_epochs()["candidates"])
        with self.assertRaises(FileNotFoundError):
            self.store.current_epoch_id()
        self.store.publish_epoch(epoch)
        self.assertEqual(self.store.current_epoch_id(), epoch)
        self.assertIn(epoch, self.store.list_epochs()["published"])

    def test_same_fact_bundle_reuses_same_epoch(self) -> None:
        first = self.store.write_candidate(self.bundle, self.analyzer.registry)
        second = self.store.write_candidate(self.bundle, self.analyzer.registry)
        self.assertEqual(first, second)

    def test_exact_lexical_edge_and_adjacency_queries(self) -> None:
        epoch = self.store.write_candidate(self.bundle, self.analyzer.registry)
        self.store.publish_epoch(epoch)
        index = self.store.index()
        widget = index.resolve_entity("pkg.model.Widget")
        self.assertIsNotNone(widget)
        entity_id = widget["identity"]["id"]
        lexical = index.search_entities("stateful example", limit=10)
        self.assertTrue(any(item["entity_id"] == entity_id for item in lexical))
        calls = index.search_edges(predicate="uceg.predicate.calls_may", limit=100)
        self.assertTrue(calls)
        neighbors = index.neighbors(entity_id, direction="out", limit=100)
        self.assertTrue(neighbors)

    def test_hybrid_search_facets_receipts_and_progressive_context(self) -> None:
        epoch = self.store.write_candidate(self.bundle, self.analyzer.registry)
        self.store.publish_epoch(epoch)
        index = self.store.index()
        results = index.hybrid_search(
            "stateful example",
            facets={"uceg.label.language": "uceg.language.python"},
            limit=10,
        )
        self.assertTrue(results)
        self.assertIn("query_receipt", results[0])
        self.assertIn("lexical", results[0]["query_receipt"]["contributing_lanes"])
        selection = index.context("stateful example", limit=1)
        self.assertEqual(selection["disclosure_level"], "selection")
        implementation = index.context("stateful example", limit=1, include_source=True)
        self.assertEqual(implementation["disclosure_level"], "implementation")
        self.assertIn("source_text", implementation["items"][0]["source"])

    def test_variant_provenance_is_queryable(self) -> None:
        epoch = self.store.write_candidate(self.bundle, self.analyzer.registry)
        self.store.publish_epoch(epoch)
        index = self.store.index()
        widget = index.resolve_entity("pkg.model.Widget")
        variants = index.representations("entity", widget["identity"]["id"])
        self.assertTrue(variants)
        self.assertTrue(all(item["generation_run_id"] for item in variants))
        self.assertTrue(any(item["representation_key"] == "uceg.name.qualified" for item in variants))

    def test_lsh_profiles_are_independently_ablated_variants(self) -> None:
        epoch = self.store.write_candidate(self.bundle, self.analyzer.registry)
        self.store.publish_epoch(epoch)
        index = self.store.index()
        widget = index.resolve_entity("pkg.model.Widget")
        variants = index.representations("entity", widget["identity"]["id"], limit=200)
        lsh_variants = [
            item
            for item in variants
            if item["representation_key"] == "uceg.block.fingerprint_lsh"
        ]
        self.assertEqual(
            {(item["value"]["algorithm"], item["value"]["profile"]) for item in lsh_variants},
            {
                ("minhash16", "narrow"),
                ("minhash16", "medium"),
                ("minhash16", "wide"),
                ("simhash64", "narrow"),
                ("simhash64", "medium"),
                ("simhash64", "wide"),
            },
        )
        self.assertTrue(
            all(
                item["value"]["collision_policy"] == "candidate_only"
                for item in lsh_variants
            )
        )

    def test_lsh_candidates_are_indexed_and_explicitly_non_proving(self) -> None:
        epoch = self.store.write_candidate(self.bundle, self.analyzer.registry)
        self.store.publish_epoch(epoch)
        candidates = self.store.index().structurally_similar("pkg.model.Widget", limit=5)
        self.assertTrue(candidates)
        self.assertTrue(candidates[0]["candidate_only"])
        self.assertTrue(candidates[0]["matching_profiles"])
        searched = candidates[0]["receipt"]["searched_profiles"]
        self.assertIn({"algorithm": "simhash64", "profile": "narrow"}, searched)
        self.assertIn({"algorithm": "minhash16", "profile": "wide"}, searched)
        self.assertIn("does not prove", candidates[0]["receipt"]["warning"])

    def test_tampered_fact_shard_fails_closed(self) -> None:
        epoch = self.store.write_candidate(self.bundle, self.analyzer.registry)
        shard = self.store.candidates / epoch / "entities.jsonl"
        shard.write_bytes(shard.read_bytes() + b"{}\n")
        with self.assertRaises(EpochValidationError):
            self.store.validate_epoch(epoch, published=False)

    def test_abandoned_build_directory_is_never_visible(self) -> None:
        self.store._ensure_layout()
        abandoned = self.store.candidates / ".building-interrupted"
        abandoned.mkdir()
        self.assertNotIn(abandoned.name, self.store.list_epochs()["candidates"])

    def test_cli_analyze_publish_and_search(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(
                [
                    "analyze",
                    "path",
                    str(GOLDEN),
                    "--store",
                    str(self.store.root),
                    "--package",
                    "pkg",
                    "--release",
                    "1.0.0",
                    "--publish",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["published"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["search", "Widget", "--store", str(self.store.root)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
