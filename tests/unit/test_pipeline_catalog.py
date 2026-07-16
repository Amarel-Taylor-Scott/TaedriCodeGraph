from __future__ import annotations

import unittest

from taedri_codegraph.pipelines import (
    ExecutionState,
    benchmark_pipeline_catalog,
    platform_pipeline_catalog,
)
from taedri_codegraph.workers import JobKind


class PipelineCatalogTests(unittest.TestCase):
    def test_working_operations_are_versioned_and_bound_to_working_stages(self) -> None:
        catalog = platform_pipeline_catalog()
        self.assertEqual(len(catalog.operations()), 6)
        self.assertTrue(catalog.digest.startswith("sha256:"))
        pipeline_operations = {
            ref
            for pipeline in catalog.pipelines()
            for stage in pipeline.stages
            if stage.execution_state is ExecutionState.WORKING
            for ref in stage.operation_refs
        }
        for operation in catalog.operations():
            self.assertEqual(operation.execution_state, ExecutionState.WORKING)
            self.assertIn(operation.ref, pipeline_operations)
            self.assertEqual(
                operation.source_execution_allowed,
                operation.operation == "verify_primitive_release",
            )
        self.assertTrue(
            all(
                stage.execution_state is ExecutionState.WORKING
                for pipeline in catalog.pipelines()
                for stage in pipeline.stages
            )
        )

    def test_github_analysis_selects_capabilities_without_hidden_default(self) -> None:
        catalog = platform_pipeline_catalog()
        contract = catalog.validate_operation(
            "ingest_github_commit",
            kind=JobKind.ACQUIRE,
            supplied_capabilities=("github-acquire", "polyglot-inventory"),
            payload={"analysis": "inventory"},
        )
        self.assertTrue(contract.network_access)
        with self.assertRaisesRegex(ValueError, "analysis must be one of"):
            contract.capabilities_for({"analysis": "mystery"})

    def test_kind_and_capability_mismatches_fail_closed(self) -> None:
        catalog = platform_pipeline_catalog()
        with self.assertRaisesRegex(ValueError, "kind does not match"):
            catalog.validate_operation(
                "ingest_pypi_wheel",
                kind=JobKind.EXTRACT,
                supplied_capabilities=("pypi-acquire", "python-ast"),
                payload={},
            )
        with self.assertRaisesRegex(ValueError, "python-ast"):
            catalog.validate_operation(
                "ingest_pypi_wheel",
                kind=JobKind.ACQUIRE,
                supplied_capabilities=("pypi-acquire",),
                payload={},
            )

    def test_benchmark_catalog_exposes_only_working_receipt_validation(self) -> None:
        pipeline = benchmark_pipeline_catalog().pipelines()[0]
        states = {stage.execution_state for stage in pipeline.stages}
        self.assertEqual(states, {ExecutionState.WORKING})
        self.assertEqual(len(pipeline.stages), 3)
        self.assertIn("without claiming to execute", pipeline.purpose)


if __name__ == "__main__":
    unittest.main()
