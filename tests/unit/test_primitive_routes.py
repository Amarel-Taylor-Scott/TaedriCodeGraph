from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.primitives.bundle import inspect_primitive_directory
from taedri_codegraph.primitives.routes import (
    BoundedPrimitiveRoutePlanner,
    PrimitiveRouteCatalog,
    PrimitiveRouteEntry,
    PrimitiveRouteError,
    PrimitiveRoutePolicy,
    PrimitiveRouteRequest,
    PrimitiveRouteStep,
    VerifiedPrimitiveRecipeRegistry,
    local_python_route_environment_digest,
)
from taedri_codegraph.primitives.wiring import (
    LocalDeterministicPythonPipelineExecutor,
    PrimitiveWiringError,
)
from tests.primitive_fixtures import requires_checked_primitive_runtime


ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"


class PrimitiveRoutePlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import json

        run = json.loads((COHORT / "run.json").read_bytes())
        records = {item["name"]: item for item in run["records"]}
        entries: list[PrimitiveRouteEntry] = []
        cls.entries_by_name: dict[str, PrimitiveRouteEntry] = {}
        cls.packs_by_id: dict[str, bytes] = {}
        for name, record in records.items():
            inspected = inspect_primitive_directory(ROOT / record["directory"])
            entry = PrimitiveRouteEntry(
                primitive_id=record["primitive_id"],
                release_id=record["release_id"],
                namespace=record["namespace"],
                name=name,
                pack_digest=record["pack_digest"],
                interface=inspected.artifacts.interface,
            )
            entries.append(entry)
            cls.entries_by_name[name] = entry
            cls.packs_by_id[entry.primitive_id] = (
                COHORT / "packs" / f"{entry.namespace}--{entry.name}.tcgpack"
            ).read_bytes()
        cls.catalog = PrimitiveRouteCatalog(entries)
        cls.planner = BoundedPrimitiveRoutePlanner(cls.catalog)
        runtimes = {entry.interface.runtime_version for entry in entries}
        if len(runtimes) != 1:
            raise AssertionError("checked route cohort must pin one runtime")
        cls.runtime = runtimes.pop()
        cls.local_runtime = f"{sys.version_info.major}.{sys.version_info.minor}"
        cls.policy = PrimitiveRoutePolicy("python", cls.runtime)

    def _step(self, name: str, query: str | None = None) -> PrimitiveRouteStep:
        entry = self.entries_by_name[name]
        return PrimitiveRouteStep(
            entry.capability_group_ids[0],
            (entry.primitive_id,),
            sha256_digest((query or name).encode()),
        )

    def _request(
        self,
        names: tuple[str, ...],
        *,
        query_suffix: str = "",
        output_schema: dict[str, object] | None = None,
        max_candidate_expansions: int = 256,
    ) -> PrimitiveRouteRequest:
        first = self.entries_by_name[names[0]].interface.input_ports[0]
        last = self.entries_by_name[names[-1]].interface.output_ports[0]
        return PrimitiveRouteRequest.create(
            input_schema=first.schema,
            output_schema=output_schema or last.schema,
            steps=tuple(
                self._step(name, name + query_suffix) for name in names
            ),
            policy=self.policy,
            max_candidate_expansions=max_candidate_expansions,
        )

    def test_retrieval_nominations_become_an_exact_executable_route(self) -> None:
        names = (
            "normalize-text",
            "collapse-whitespace",
            "casefold-text",
            "normalize-column-name",
        )
        request = self._request(names)
        result = self.planner.search(request)
        self.assertEqual(result.receipt.source, "bounded_graph_search")
        self.assertEqual(result.receipt.model_calls, 0)
        self.assertEqual(len(result.routes), 1)
        route = result.routes[0]
        self.assertEqual(
            route.primitive_ids,
            tuple(self.entries_by_name[name].primitive_id for name in names),
        )
        executor = LocalDeterministicPythonPipelineExecutor()
        packs = tuple(self.packs_by_id[item] for item in route.primitive_ids)
        if self.runtime != self.local_runtime:
            with self.assertRaisesRegex(PrimitiveWiringError, "pipeline pins Python"):
                executor.execute(route.plan, packs, "  Customer\t Straße  ")
            return
        execution = executor.execute(route.plan, packs, "  Customer\t Straße  ")
        self.assertEqual(execution.output, "customer_strasse")
        self.assertEqual(execution.receipt.pack_digests, route.pack_digests)

    def test_schema_blocking_abstains_without_inventing_an_adapter(self) -> None:
        request = self._request(
            ("numeric-mean",),
            output_schema={"type": "string"},
        )
        result = self.planner.search(request)
        self.assertEqual(result.routes, ())
        self.assertEqual(result.receipt.stop_reason, "no_compatible_route")
        self.assertEqual(result.receipt.terminal_output_rejection_count, 1)

    def test_wrong_capability_nomination_is_not_reinterpreted(self) -> None:
        normalize = self.entries_by_name["normalize-text"]
        mean = self.entries_by_name["numeric-mean"]
        step = PrimitiveRouteStep(
            normalize.capability_group_ids[0],
            (mean.primitive_id,),
            sha256_digest(b"wrong nomination"),
        )
        request = PrimitiveRouteRequest.create(
            input_schema=normalize.interface.input_ports[0].schema,
            output_schema=normalize.interface.output_ports[0].schema,
            steps=(step,),
            policy=self.policy,
        )
        result = self.planner.search(request)
        self.assertEqual(result.routes, ())
        self.assertEqual(result.receipt.considered_candidate_count, 0)

    def test_candidate_expansion_budget_is_explicit(self) -> None:
        names = ("minmax-scale", "numeric-mean")
        request = self._request(names, max_candidate_expansions=1)
        result = self.planner.search(request)
        self.assertEqual(result.routes, ())
        self.assertEqual(
            result.receipt.stop_reason,
            "candidate_expansion_budget_exhausted",
        )
        self.assertEqual(result.receipt.considered_candidate_count, 1)

    @requires_checked_primitive_runtime
    def test_verified_recipe_reuse_skips_candidate_and_wire_search(self) -> None:
        names = ("minmax-scale", "numeric-mean")
        request = self._request(names)
        searched = self.planner.search(request)
        route = searched.routes[0]
        execution = LocalDeterministicPythonPipelineExecutor().execute(
            route.plan,
            tuple(self.packs_by_id[item] for item in route.primitive_ids),
            [10, 20, 30],
        )
        registry = VerifiedPrimitiveRecipeRegistry()
        environment = local_python_route_environment_digest(self.runtime)
        recipe = registry.record(
            route=route,
            execution_receipt=execution.receipt,
            environment_digest=environment,
            verifier_id="taedri.route-verifier.v1",
            verified_at="2026-07-17T07:00:00Z",
        )
        paraphrase = self._request(names, query_suffix=" paraphrase")
        self.assertNotEqual(request.identity.id, paraphrase.identity.id)
        self.assertEqual(request.contract_digest, paraphrase.contract_digest)
        reused = self.planner.resolve(
            paraphrase,
            recipe_registry=registry,
            environment_digest=environment,
        )
        self.assertEqual(reused.routes, (route,))
        self.assertEqual(reused.receipt.source, "verified_recipe")
        self.assertEqual(reused.receipt.verified_recipe_id, recipe.identity.id)
        self.assertEqual(reused.receipt.considered_candidate_count, 0)
        self.assertEqual(reused.receipt.wire_assessment_count, 0)

    @requires_checked_primitive_runtime
    def test_recipe_registry_rejects_receipts_for_another_plan(self) -> None:
        numeric = self.planner.search(
            self._request(("minmax-scale", "numeric-mean"))
        ).routes[0]
        text = self.planner.search(
            self._request(("normalize-text", "casefold-text"))
        ).routes[0]
        text_execution = LocalDeterministicPythonPipelineExecutor().execute(
            text.plan,
            tuple(self.packs_by_id[item] for item in text.primitive_ids),
            " Value ",
        )
        with self.assertRaisesRegex(PrimitiveRouteError, "another plan"):
            VerifiedPrimitiveRecipeRegistry().record(
                route=numeric,
                execution_receipt=text_execution.receipt,
                environment_digest=local_python_route_environment_digest(
                    self.runtime
                ),
                verifier_id="taedri.route-verifier.v1",
                verified_at="2026-07-17T07:00:00Z",
            )

    @requires_checked_primitive_runtime
    def test_recipe_registry_rejects_stale_receipt_identity(self) -> None:
        route = self.planner.search(
            self._request(("normalize-text", "casefold-text"))
        ).routes[0]
        execution = LocalDeterministicPythonPipelineExecutor().execute(
            route.plan,
            tuple(self.packs_by_id[item] for item in route.primitive_ids),
            " Value ",
        )
        forged = replace(
            execution.receipt,
            output_digest="sha256:" + "0" * 64,
        )
        with self.assertRaisesRegex(PrimitiveRouteError, "identity"):
            VerifiedPrimitiveRecipeRegistry().record(
                route=route,
                execution_receipt=forged,
                environment_digest=local_python_route_environment_digest(
                    self.runtime
                ),
                verifier_id="taedri.route-verifier.v1",
                verified_at="2026-07-17T07:00:00Z",
            )

    def test_catalog_rejects_duplicate_release_identity(self) -> None:
        entry = self.entries_by_name["normalize-text"]
        duplicate = replace(entry, primitive_id=self.entries_by_name["casefold-text"].primitive_id)
        with self.assertRaisesRegex(PrimitiveRouteError, "release ID"):
            PrimitiveRouteCatalog((entry, duplicate))


if __name__ == "__main__":
    unittest.main()
