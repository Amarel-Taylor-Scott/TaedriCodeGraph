from __future__ import annotations

import unittest

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.canonical import canonical_digest
from taedri_codegraph.contracts import ProducerRef, SubjectRef, TypedValue, ValueKind
from taedri_codegraph.providers import (
    CallbackProvider,
    ProviderDescriptor,
    ProviderInput,
    ProviderOutput,
    ProviderRegistry,
    RouteCandidate,
    record_route_decision,
    run_provider,
)
from taedri_codegraph.representations import RepresentationDescriptor

from tests.helpers import GOLDEN


class ProviderAndRouterTests(unittest.TestCase):
    def test_nondeterministic_attempts_retain_parallel_provenance(self) -> None:
        analyzer = PythonSyntaxAnalyzer()
        bundle = analyzer.analyze(GOLDEN, package_name="pkg")
        widget = next(
            item for item in bundle.entities.values() if item.qualified_name == "pkg.model.Widget"
        )
        output_descriptor = RepresentationDescriptor(
            "example.family.label",
            "example.label.intent",
            "1.0.0",
            "https://example.test/models",
            ("entity",),
            (ValueKind.KEYWORD,),
            ("facet", "lexical"),
        )
        provider = CallbackProvider(
            ProviderDescriptor(
                "example.llm-labeler",
                "2.0.0",
                "https://example.test/models",
                False,
                ("classification",),
                (output_descriptor,),
                network_required=True,
            ),
            lambda _: (ProviderOutput("example.family.label", "example.label.intent", TypedValue(ValueKind.KEYWORD, "stateful-model"), 820_000),),
        )
        request = ProviderInput(SubjectRef("entity", widget.identity.id), {"name": widget.qualified_name})
        first = run_provider(
            bundle,
            provider,
            (request,),
            attempt_key="attempt-001",
            model_config={"temperature_decimal": "0.2"},
        )
        second = run_provider(
            bundle,
            provider,
            (request,),
            attempt_key="attempt-002",
            model_config={"temperature_decimal": "0.2"},
        )
        self.assertNotEqual(first, second)
        matching = [
            item
            for item in bundle.representation_assertions.values()
            if bundle.representation_contents[item.content_id].representation_key
            == "example.label.intent"
        ]
        self.assertEqual(len(matching), 2)
        self.assertEqual(len({item.content_id for item in matching}), 1)
        providers = ProviderRegistry()
        providers.register(provider)
        bundle.validate(analyzer.registry.resolve, providers.representation_registry().resolve)

    def test_router_monitor_receipt_is_not_a_mutable_log_line(self) -> None:
        analyzer = PythonSyntaxAnalyzer()
        bundle = analyzer.analyze(GOLDEN, package_name="pkg")
        producer = ProducerRef("test.router", "1.0.0", canonical_digest({"policy": 1}))
        run_id = record_route_decision(
            bundle,
            task_key="uceg.task.describe_code",
            policy_key="test.policy.cost-aware",
            policy_version="1.0.0",
            candidates=(
                RouteCandidate("local.labeler", "1.0.0", True, "lowest cost", 0, 5),
                RouteCandidate("frontier.llm", "2026-07", True, "fallback", 2000, 800),
            ),
            selected_provider="local.labeler@1.0.0",
            input_digest=canonical_digest({"entity": "widget"}),
            producer=producer,
            attempt_key="route-001",
        )
        self.assertIn(run_id, bundle.generation_runs)
        self.assertTrue(
            any(
                content.representation_key == "uceg.router.decision"
                for content in bundle.representation_contents.values()
            )
        )


if __name__ == "__main__":
    unittest.main()
