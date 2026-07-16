from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

from taedri_codegraph.primitives.bundle import inspect_primitive_directory
from taedri_codegraph.primitives.wiring import (
    ExactPrimitiveWirePlanner,
    LocalDeterministicPythonPipelineExecutor,
    PrimitiveWiringError,
    WireVerdict,
)


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval/results/deterministic-primitive-pipeline-2026-07-16"


class DeterministicPrimitiveWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.normalize = inspect_primitive_directory(
            ROOT / "examples/primitives/normalize-text"
        ).artifacts.interface
        cls.casefold = inspect_primitive_directory(
            ROOT / "examples/primitives/casefold-text"
        ).artifacts.interface

    def test_real_ports_produce_an_exact_adapter_free_plan(self) -> None:
        planner = ExactPrimitiveWirePlanner()
        assessment = planner.assess(self.normalize, self.casefold)
        self.assertEqual(assessment.verdict, WireVerdict.COMPATIBLE)
        plan = planner.pipeline((self.normalize, self.casefold))
        self.assertEqual(len(plan.wires), 1)
        self.assertEqual(plan.wires[0].transport, "python_native")
        self.assertTrue(plan.identity.id.startswith("uceg:v1:deterministic_pipeline_plan:"))

    def test_schema_mismatch_is_incompatible_and_never_infers_an_adapter(self) -> None:
        port = replace(
            self.casefold.input_ports[0],
            schema={"type": "integer"},
            schema_digest="sha256:" + "0" * 64,
        )
        incompatible = replace(
            self.casefold,
            ports=(port, *self.casefold.output_ports),
        )
        planner = ExactPrimitiveWirePlanner()
        self.assertEqual(
            planner.assess(self.normalize, incompatible).verdict,
            WireVerdict.INCOMPATIBLE,
        )
        with self.assertRaisesRegex(PrimitiveWiringError, "not proven compatible"):
            planner.connect(self.normalize, incompatible)

    def test_checked_in_packs_execute_deterministically_without_model_or_rewrite(self) -> None:
        plan = ExactPrimitiveWirePlanner().pipeline((self.normalize, self.casefold))
        packs = (
            (RESULTS / "normalize-text.tcgpack").read_bytes(),
            (RESULTS / "casefold-text.tcgpack").read_bytes(),
        )
        executor = LocalDeterministicPythonPipelineExecutor()
        expected_runtime = f"{sys.version_info.major}.{sys.version_info.minor}"
        if self.normalize.runtime_version != expected_runtime:
            with self.assertRaisesRegex(PrimitiveWiringError, "pipeline pins Python"):
                executor.execute(plan, packs, "  Straße  ")
            return
        first = executor.execute(plan, packs, "  Straße  ")
        second = executor.execute(plan, packs, "  Straße  ")
        self.assertEqual(first.output, "strasse")
        self.assertEqual(first.receipt, second.receipt)
        self.assertEqual(first.receipt.executed_stage_count, 2)

    def test_executor_rejects_a_plan_for_another_python_minor(self) -> None:
        expected_runtime = f"{sys.version_info.major}.{sys.version_info.minor}"
        other_runtime = "99.99" if expected_runtime != "99.99" else "98.98"
        incompatible = replace(self.normalize, runtime_version=other_runtime)
        plan = ExactPrimitiveWirePlanner().pipeline((incompatible,))
        with self.assertRaisesRegex(PrimitiveWiringError, "pipeline pins Python"):
            LocalDeterministicPythonPipelineExecutor().execute(
                plan,
                ((RESULTS / "normalize-text.tcgpack").read_bytes(),),
                " value ",
            )

    def test_executor_rejects_interface_fields_not_bound_by_the_pack_graph(self) -> None:
        expected_runtime = f"{sys.version_info.major}.{sys.version_info.minor}"
        forged = replace(
            self.normalize,
            entrypoint="not_the_bound_symbol",
            runtime_version=expected_runtime,
        )
        companion = replace(self.casefold, runtime_version=expected_runtime)
        plan = ExactPrimitiveWirePlanner().pipeline((forged, companion))
        packs = (
            (RESULTS / "normalize-text.tcgpack").read_bytes(),
            (RESULTS / "casefold-text.tcgpack").read_bytes(),
        )
        with self.assertRaisesRegex(PrimitiveWiringError, "entrypoint"):
            LocalDeterministicPythonPipelineExecutor().execute(
                plan,
                packs,
                " value ",
            )


if __name__ == "__main__":
    unittest.main()
