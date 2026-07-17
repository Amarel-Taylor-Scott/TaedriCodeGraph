from __future__ import annotations

import json
import unittest
from pathlib import Path

from taedri_codegraph.prompt_interception import (
    DeterministicBM25Shortlister,
    PromptInterceptor,
    ReleasedPrimitiveCatalog,
    RetrievalArm,
    load_natural_primitive_tasks,
)
from tests.prompt_interception_fakes import SemanticFakeChatProvider

ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"
TASKS = ROOT / "fixtures/prompt-interception/natural-tasks.json"


class PromptInterceptionUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = ReleasedPrimitiveCatalog.load_checked_cohort(COHORT)
        cls.tasks = load_natural_primitive_tasks(TASKS)

    def test_checked_cards_bind_exact_releases_and_pack_handles(self) -> None:
        self.assertEqual(len(self.catalog.cards), 11)
        for card in self.catalog.cards:
            self.assertTrue(card.primitive_id.startswith("uceg:v1:primitive:"))
            self.assertTrue(card.release_id.startswith("uceg:v1:primitive_release:"))
            self.assertTrue(card.pack_id.startswith("uceg:v1:primitive_pack:"))
            self.assertRegex(card.pack_digest, r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(card.pack_location, card.artifact_handle.location)
            encoded, interface = self.catalog.resolve(card.artifact_handle)
            self.assertEqual(len(encoded), card.artifact_handle.size_bytes)
            self.assertTrue(interface.deterministic)

    def test_teacher_prompt_uses_compact_handles_and_withholds_bodies_and_cases(self) -> None:
        task = self.tasks[0]
        interceptor = PromptInterceptor(
            self.catalog, SemanticFakeChatProvider(), shortlist_limit=4
        )
        messages, ranking = interceptor.messages(task, RetrievalArm.FULL_CATALOG)
        self.assertEqual(len(ranking), len(self.catalog.cards))
        prompt = messages[-1].content
        payload = json.loads(prompt)
        self.assertEqual(payload["task_request"], task.request)
        self.assertEqual(payload["primitive_cards"][0]["route_handle"], "c001")
        self.assertNotIn("uceg:v1:", prompt)
        self.assertNotIn("pack_digest", prompt)
        self.assertNotIn("artifact_handle", prompt)
        self.assertNotIn(task.hidden_cases[0].expected_output, prompt)
        self.assertNotIn('return " ".join(value.split())', prompt)

    def test_shortlist_is_weighted_deterministic_and_fail_closed_at_zero_evidence(self) -> None:
        shortlister = DeterministicBM25Shortlister(self.catalog.cards)
        query = "turn deeply nested dictionaries into flat dotted keys"
        first = shortlister.shortlist(query, 4)
        second = shortlister.shortlist(query, 4)
        self.assertEqual(first, second)
        self.assertEqual(self.catalog.card(first[0].primitive_id).name, "flatten-record")
        unsupported = shortlister.shortlist(
            "quasar xylophone astrophysics orbital spectroscopy", 4
        )
        self.assertEqual(unsupported, ())

    def test_teacher_can_explicitly_abstain_and_usage_is_retained(self) -> None:
        provider = SemanticFakeChatProvider(
            forced_content=(
                '{"reason_code":"no_suitable_candidate",'
                '"selected_route_handle":null}'
            )
        )
        task = self.tasks[0]
        receipt = PromptInterceptor(
            self.catalog, provider, shortlist_limit=4
        ).intercept(
            task,
            RetrievalArm.FULL_CATALOG,
            model="fake-model",
            seed=7,
            max_completion_tokens=64,
        )
        self.assertEqual(receipt.status, "teacher_rejected")
        self.assertEqual(
            receipt.error_code, "teacher_abstained_no_suitable_candidate"
        )
        self.assertIsNone(receipt.artifact_handle)
        self.assertGreater(receipt.model_usage.prompt_tokens, 0)
        encoded = json.dumps(receipt.to_dict(), sort_keys=True)
        self.assertNotIn(task.request, encoded)
        receipt.identity.validate()

    def test_teacher_output_must_select_a_candidate_handle_exactly(self) -> None:
        provider = SemanticFakeChatProvider(
            forced_content=(
                '{"selected_route_handle":"c999",'
                '"reason_code":"capability_match"}'
            )
        )
        receipt = PromptInterceptor(
            self.catalog, provider, shortlist_limit=4
        ).intercept(
            self.tasks[0],
            RetrievalArm.DETERMINISTIC_SHORTLIST,
            model="fake-model",
            seed=0,
            max_completion_tokens=64,
        )
        self.assertEqual(receipt.status, "teacher_rejected")
        self.assertEqual(
            receipt.error_code, "teacher_selection_outside_candidates"
        )


if __name__ == "__main__":
    unittest.main()

