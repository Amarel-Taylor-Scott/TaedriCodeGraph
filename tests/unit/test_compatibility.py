from __future__ import annotations

import unittest

from taedri_codegraph.compatibility import (
    CompatibilityRequirementSet,
    CompatibilitySignature,
    CompatibilityVerdict,
    DimensionValue,
    ExactCompatibilityEvaluator,
)


class CompatibilityPoisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = ExactCompatibilityEvaluator()
        self.requirements = CompatibilityRequirementSet(
            purpose="compose_output_to_input",
            required_dimensions=("uceg.compat.type", "uceg.compat.async_mode"),
            prohibited_values={},
        )

    def signature(
        self, subject: str, *, orientation: str = "provides", **values: str
    ) -> CompatibilitySignature:
        return CompatibilitySignature(
            subject,
            orientation,
            {
                key: DimensionValue(value, True, (f"evidence:{key}:{value}",))
                for key, value in values.items()
            },
        )

    def test_missing_is_unknown_not_wildcard(self) -> None:
        producer = self.signature("producer", **{"uceg.compat.type": "int"})
        consumer = self.signature(
            "consumer",
            orientation="requires",
            **{"uceg.compat.type": "int", "uceg.compat.async_mode": "sync"},
        )
        result = self.evaluator.evaluate(producer, consumer, self.requirements)
        self.assertEqual(result.verdict, CompatibilityVerdict.UNKNOWN)

    def test_authoritative_mismatch_is_incompatible(self) -> None:
        producer = self.signature(
            "producer", **{"uceg.compat.type": "int", "uceg.compat.async_mode": "sync"}
        )
        consumer = self.signature(
            "consumer",
            orientation="requires",
            **{"uceg.compat.type": "str", "uceg.compat.async_mode": "sync"},
        )
        result = self.evaluator.evaluate(producer, consumer, self.requirements)
        self.assertEqual(result.verdict, CompatibilityVerdict.INCOMPATIBLE)

    def test_all_required_authoritative_matches_are_compatible(self) -> None:
        dimensions = {"uceg.compat.type": "int", "uceg.compat.async_mode": "sync"}
        result = self.evaluator.evaluate(
            self.signature("producer", **dimensions),
            self.signature("consumer", orientation="requires", **dimensions),
            self.requirements,
        )
        self.assertEqual(result.verdict, CompatibilityVerdict.COMPATIBLE)

    def test_orientation_alone_is_unknown_without_a_required_dimension(self) -> None:
        requirements = CompatibilityRequirementSet(
            purpose="compose_output_to_input",
            required_dimensions=(),
            prohibited_values={},
        )
        result = self.evaluator.evaluate(
            self.signature("producer"),
            self.signature("consumer", orientation="requires"),
            requirements,
        )
        self.assertEqual(result.verdict, CompatibilityVerdict.UNKNOWN)
        self.assertEqual(
            [item.dimension_key for item in result.dimensions],
            ["uceg.compat.orientation", "uceg.compat.required_dimension"],
        )

    def test_low_authority_cannot_create_incompatibility(self) -> None:
        producer = CompatibilitySignature(
            "producer",
            "provides",
            {
                "uceg.compat.type": DimensionValue("int", False),
                "uceg.compat.async_mode": DimensionValue("sync", True),
            },
        )
        consumer = self.signature(
            "consumer",
            orientation="requires",
            **{"uceg.compat.type": "str", "uceg.compat.async_mode": "sync"},
        )
        result = self.evaluator.evaluate(producer, consumer, self.requirements)
        self.assertEqual(result.verdict, CompatibilityVerdict.UNKNOWN)

    def test_reversed_orientation_is_incompatible_even_when_values_match(self) -> None:
        dimensions = {"uceg.compat.type": "int", "uceg.compat.async_mode": "sync"}
        result = self.evaluator.evaluate(
            self.signature("producer", orientation="requires", **dimensions),
            self.signature("consumer", orientation="provides", **dimensions),
            self.requirements,
        )
        self.assertEqual(result.verdict, CompatibilityVerdict.INCOMPATIBLE)
        self.assertEqual(result.dimensions[0].dimension_key, "uceg.compat.orientation")


if __name__ == "__main__":
    unittest.main()
