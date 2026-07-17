from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

from taedri_codegraph.prompt_interception import ReleasedPrimitiveCatalog
from taedri_codegraph.primitives.retrieval_program import (
    PrimitiveRetrievalIndex,
    RetrievalDocument,
    RetrievalFamily,
    RetrievalPathStatus,
    RetrievalProgramError,
    RetrievalProgramRegistry,
    default_primitive_retrieval_program,
)


ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"


class PrimitiveRetrievalProgramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = ReleasedPrimitiveCatalog.load_checked_cohort(COHORT)
        cls.documents = tuple(
            RetrievalDocument(
                card.primitive_id,
                card.namespace,
                card.name,
                card.summary,
                card.keywords,
                card.use_cases,
            )
            for card in cls.catalog.cards
        )
        cls.by_id = {card.primitive_id: card for card in cls.catalog.cards}

    def test_exact_name_stops_after_one_hot_path_with_complete_receipts(self) -> None:
        execution = PrimitiveRetrievalIndex(self.documents).execute(
            "normalize-iso-datetime",
            default_primitive_retrieval_program(),
            limit=4,
        )
        self.assertEqual(execution.stop_reason, "unique_exact_match")
        self.assertEqual(execution.consumed_cost_units, 1)
        self.assertEqual(len(execution.candidates), 1)
        self.assertEqual(
            self.by_id[execution.candidates[0].primitive_id].name,
            "normalize-iso-datetime",
        )
        self.assertEqual(len(execution.path_receipts), 6)
        self.assertEqual(
            execution.path_receipts[0].status, RetrievalPathStatus.EXECUTED
        )
        self.assertTrue(
            all(
                item.status is RetrievalPathStatus.SKIPPED_POLICY
                for item in execution.path_receipts[1:]
            )
        )

    def test_paraphrase_fuses_paths_and_abstains_without_grounded_evidence(self) -> None:
        index = PrimitiveRetrievalIndex(self.documents)
        program = default_primitive_retrieval_program()
        first = index.execute(
            "map blank and N/A sentinel strings to a missing value",
            program,
            limit=4,
        )
        second = index.execute(
            "map blank and N/A sentinel strings to a missing value",
            program,
            limit=4,
        )
        self.assertEqual(first, second)
        self.assertEqual(self.by_id[first.candidates[0].primitive_id].name, "normalize-null-marker")
        self.assertGreater(len(first.candidates[0].contributions), 1)
        unsupported = index.execute(
            "quasar xylophone astrophysics orbital spectroscopy",
            program,
            limit=4,
        )
        self.assertEqual(unsupported.candidates, ())
        self.assertEqual(unsupported.stop_reason, "no_grounded_candidates")
        lexical_hash = next(
            item
            for item in unsupported.path_receipts
            if item.family is RetrievalFamily.LEXICAL_HASH
        )
        self.assertEqual(lexical_hash.candidate_count, 0)

    def test_true_semantic_lane_is_optional_separate_and_receipted(self) -> None:
        target = next(
            item for item in self.documents if item.name == "normalize-iso-datetime"
        )

        def semantic(request, documents, limit):
            self.assertEqual(request, "chronological universalization")
            self.assertEqual(documents, self.documents)
            self.assertEqual(limit, 32)
            return {target.primitive_id: 910_000}

        execution = PrimitiveRetrievalIndex(
            self.documents, semantic_retriever=semantic
        ).execute(
            "chronological universalization",
            default_primitive_retrieval_program(),
            limit=4,
            capabilities=("taedri.capability.semantic_embeddings",),
        )
        self.assertEqual(
            self.by_id[execution.candidates[0].primitive_id].name,
            "normalize-iso-datetime",
        )
        semantic_receipt = next(
            item
            for item in execution.path_receipts
            if item.family is RetrievalFamily.SEMANTIC
        )
        self.assertEqual(semantic_receipt.status, RetrievalPathStatus.EXECUTED)
        self.assertEqual(semantic_receipt.new_candidate_count, 1)
        lexical_receipt = next(
            item
            for item in execution.path_receipts
            if item.family is RetrievalFamily.LEXICAL_HASH
        )
        self.assertEqual(lexical_receipt.candidate_count, 0)

    def test_registry_is_additive_and_budget_skips_are_explicit(self) -> None:
        program = default_primitive_retrieval_program()
        registry = RetrievalProgramRegistry()
        registry.register(program)
        registry.register(program)
        self.assertIs(registry.resolve(program.ref), program)
        with self.assertRaisesRegex(RetrievalProgramError, "cannot reinterpret"):
            registry.register(dataclasses.replace(program, maximum_cost_units=14))
        constrained = dataclasses.replace(program, maximum_cost_units=1)
        execution = PrimitiveRetrievalIndex(self.documents).execute(
            "clean missing sentinel values", constrained, limit=4
        )
        self.assertTrue(
            any(
                item.status is RetrievalPathStatus.SKIPPED_BUDGET
                for item in execution.path_receipts
            )
        )


if __name__ == "__main__":
    unittest.main()
