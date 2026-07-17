from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.canonical import canonical_json_bytes
from taedri_codegraph.issue_workloads import (
    IssueWorkloadError,
    load_issue_grounded_workload,
    normalized_issue_source_digest,
)
from taedri_codegraph.prompt_interception import (
    PromptInterceptor,
    ReleasedPrimitiveCatalog,
    RetrievalArm,
    load_natural_primitive_tasks,
    run_prompt_interception_campaign,
)
from tests.prompt_interception_fakes import SemanticFakeChatProvider

ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"
WORKLOAD = (
    ROOT
    / "fixtures/prompt-interception/external-github-issues-positive-v1.json"
)


class ExternalIssueWorkloadIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = ReleasedPrimitiveCatalog.load_checked_cohort(COHORT)
        cls.workload = load_issue_grounded_workload(WORKLOAD)

    def test_sources_are_bound_and_claim_scope_is_explicit(self) -> None:
        expected_sources = {
            "github_pandas_9346.stable_unique": (
                "pandas-dev/pandas",
                9346,
                "DOC/TST: is pd.unique and the order it returns API?",
            ),
            "github_more_itertools_980.chunk_rows": (
                "more-itertools/more-itertools",
                980,
                "ichunked function iterator does not iterate when I'm trying to split Cassandra results",
            ),
            "github_pandas_12286.flatten_mapping": (
                "pandas-dev/pandas",
                12286,
                "Feature suggestion: flexible hierarchical data (json) importer (will implement if interest exists)",
            ),
            "github_sklearn_27987.minmax_constant": (
                "scikit-learn/scikit-learn",
                27987,
                "`MinMaxScalar.fit_transform()` Returns Zero When All Elements Are Same",
            ),
            "github_sklearn_17794.zscore_constant": (
                "scikit-learn/scikit-learn",
                17794,
                " _handle_zeros_in_scale causing improper scaling when using StandardScaler()",
            ),
        }
        self.assertEqual(len(self.workload.tasks), 5)
        self.assertTrue(
            any(
                "not a full coding benchmark" in item.lower()
                for item in self.workload.claim_limitations
            )
        )
        for item in self.workload.tasks:
            self.assertEqual(
                (
                    item.source.repository,
                    item.source.issue_number,
                    item.source.issue_title,
                ),
                expected_sources[item.task.task_id],
            )
            self.assertEqual(item.source.accessed_on, "2026-07-16")
            self.assertEqual(
                item.source.normalized_source_digest,
                normalized_issue_source_digest(
                    repository=item.source.repository,
                    issue_number=item.source.issue_number,
                    issue_title=item.source.issue_title,
                    source_excerpt=item.source.source_excerpt,
                ),
            )

    def test_plain_task_loader_and_teacher_prompt_exclude_provenance_and_cases(self) -> None:
        plain_tasks = load_natural_primitive_tasks(WORKLOAD)
        self.assertEqual(plain_tasks, self.workload.natural_tasks)
        for item in self.workload.tasks:
            task_payload = item.task.to_dict()
            self.assertEqual(
                set(task_payload),
                {
                    "task_id",
                    "trajectory_id",
                    "step_index",
                    "domain",
                    "request",
                    "hidden_cases",
                },
            )
            messages, _ = PromptInterceptor(
                self.catalog, SemanticFakeChatProvider(), shortlist_limit=4
            ).messages(item.task, RetrievalArm.FULL_CATALOG)
            prompt_payload = json.loads(messages[-1].content)
            self.assertEqual(
                set(prompt_payload),
                {"schema_version", "task_request", "primitive_cards"},
            )
            prompt = messages[-1].content
            self.assertNotIn(item.source.issue_url, prompt)
            self.assertNotIn(item.source.issue_title, prompt)
            self.assertNotIn(item.source.accessed_on, prompt)
            for case in item.task.hidden_cases:
                self.assertNotIn(
                    canonical_json_bytes(case.input_value).decode("utf-8"), prompt
                )
                self.assertNotIn(
                    canonical_json_bytes(case.expected_output).decode("utf-8"),
                    prompt,
                )

    def test_hidden_cases_are_independent_of_archived_issue_examples(self) -> None:
        for item in self.workload.tasks:
            self.assertGreaterEqual(len(item.task.hidden_cases), 2)
            evidence = item.source.source_excerpt
            for case in item.task.hidden_cases:
                self.assertNotIn(
                    canonical_json_bytes(case.input_value).decode("utf-8"), evidence
                )
                self.assertNotIn(
                    canonical_json_bytes(case.expected_output).decode("utf-8"),
                    evidence,
                )

    def test_local_matched_campaign_selects_and_executes_expected_primitives(self) -> None:
        expected_names = {
            item.task.task_id: item.expected_primitive.name
            for item in self.workload.tasks
        }
        campaign = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=self.workload.natural_tasks,
            provider=SemanticFakeChatProvider(),
            provider_id="fake",
            model="semantic-fake-v1",
            seeds=(41,),
            max_completion_tokens=64,
            shortlist_limit=4,
        )
        self.assertEqual(len(campaign.arms), 10)
        self.assertEqual(len(campaign.matched_pairs), 5)
        self.assertTrue(all(item.status == "accepted" for item in campaign.arms))
        for arm in campaign.arms:
            self.assertIsNotNone(arm.interception)
            assert arm.interception is not None
            selected = self.catalog.card(
                str(arm.interception.selected_primitive_id)
            )
            self.assertEqual(selected.name, expected_names[arm.task_id])
            self.assertIsNotNone(arm.verification)
            assert arm.verification is not None
            self.assertEqual(arm.verification.executed_case_count, 2)
            self.assertEqual(arm.verification.passed_case_count, 2)

    def test_loader_rejects_mutated_digest_and_unbound_issue_url(self) -> None:
        raw = json.loads(WORKLOAD.read_text(encoding="utf-8"))
        mutations = []
        bad_digest = copy.deepcopy(raw)
        bad_digest["tasks"][0]["source_provenance"][
            "normalized_source_digest"
        ] = "sha256:" + "0" * 64
        mutations.append(bad_digest)
        bad_url = copy.deepcopy(raw)
        bad_url["tasks"][0]["source_provenance"]["issue_url"] = (
            "https://github.com/pandas-dev/pandas/issues/9347"
        )
        mutations.append(bad_url)
        missing_metadata = copy.deepcopy(raw)
        del missing_metadata["tasks"][0]["source_provenance"]
        mutations.append(missing_metadata)

        for mutation_index, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation_index):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "workload.json"
                    path.write_text(json.dumps(mutation), encoding="utf-8")
                    self.assertEqual(
                        load_natural_primitive_tasks(path),
                        self.workload.natural_tasks,
                    )
                    with self.assertRaises(IssueWorkloadError):
                        load_issue_grounded_workload(path)


if __name__ == "__main__":
    unittest.main()
