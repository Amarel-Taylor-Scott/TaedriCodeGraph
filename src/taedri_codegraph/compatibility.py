"""Sparse, directional compatibility contracts with explicit unknown semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class CompatibilityVerdict(str, Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DimensionValue:
    value: Any
    authoritative: bool
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompatibilitySignature:
    subject_id: str
    orientation: str
    dimensions: Mapping[str, DimensionValue]

    def __post_init__(self) -> None:
        if self.orientation not in {"provides", "requires", "bidirectional"}:
            raise ValueError("invalid compatibility orientation")


@dataclass(frozen=True, slots=True)
class CompatibilityRequirementSet:
    purpose: str
    required_dimensions: tuple[str, ...]
    prohibited_values: Mapping[str, tuple[Any, ...]]


@dataclass(frozen=True, slots=True)
class DimensionAssessment:
    dimension_key: str
    verdict: CompatibilityVerdict
    reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompatibilityAssessment:
    producer_id: str
    consumer_id: str
    purpose: str
    verdict: CompatibilityVerdict
    dimensions: tuple[DimensionAssessment, ...]


class ExactCompatibilityEvaluator:
    """A deliberately conservative exact evaluator for registered scalar dimensions."""

    def evaluate(
        self,
        producer: CompatibilitySignature,
        consumer: CompatibilitySignature,
        requirements: CompatibilityRequirementSet,
    ) -> CompatibilityAssessment:
        producer_oriented = producer.orientation in {"provides", "bidirectional"}
        consumer_oriented = consumer.orientation in {"requires", "bidirectional"}
        orientation_verdict = (
            CompatibilityVerdict.COMPATIBLE
            if producer_oriented and consumer_oriented
            else CompatibilityVerdict.INCOMPATIBLE
        )
        assessments: list[DimensionAssessment] = [
            DimensionAssessment(
                "uceg.compat.orientation",
                orientation_verdict,
                (
                    "producer provides and consumer requires"
                    if orientation_verdict is CompatibilityVerdict.COMPATIBLE
                    else "producer/consumer orientations are reversed or unsupported"
                ),
                (),
            )
        ]
        if not requirements.required_dimensions:
            assessments.append(
                DimensionAssessment(
                    "uceg.compat.required_dimension",
                    CompatibilityVerdict.UNKNOWN,
                    (
                        "at least one authoritative required dimension is needed; "
                        "orientation alone is not compatibility proof"
                    ),
                    (),
                )
            )
        for dimension in requirements.required_dimensions:
            provided = producer.dimensions.get(dimension)
            required = consumer.dimensions.get(dimension)
            evidence = tuple(
                sorted(
                    set((provided.evidence_ids if provided else ()))
                    | set((required.evidence_ids if required else ()))
                )
            )
            if provided is None or required is None:
                assessments.append(
                    DimensionAssessment(
                        dimension,
                        CompatibilityVerdict.UNKNOWN,
                        "required dimension is missing; missing is not a wildcard",
                        evidence,
                    )
                )
                continue
            prohibited = requirements.prohibited_values.get(dimension, ())
            if provided.value in prohibited:
                verdict = (
                    CompatibilityVerdict.INCOMPATIBLE
                    if provided.authoritative
                    else CompatibilityVerdict.UNKNOWN
                )
                assessments.append(
                    DimensionAssessment(
                        dimension,
                        verdict,
                        "provided value is prohibited"
                        if verdict is CompatibilityVerdict.INCOMPATIBLE
                        else "prohibition is supported only by non-authoritative evidence",
                        evidence,
                    )
                )
                continue
            if provided.value != required.value:
                authoritative = provided.authoritative and required.authoritative
                assessments.append(
                    DimensionAssessment(
                        dimension,
                        CompatibilityVerdict.INCOMPATIBLE
                        if authoritative
                        else CompatibilityVerdict.UNKNOWN,
                        "authoritative exact values differ"
                        if authoritative
                        else "values differ but decisive authority is absent",
                        evidence,
                    )
                )
            else:
                authoritative = provided.authoritative and required.authoritative
                assessments.append(
                    DimensionAssessment(
                        dimension,
                        CompatibilityVerdict.COMPATIBLE
                        if authoritative
                        else CompatibilityVerdict.UNKNOWN,
                        "authoritative exact values match"
                        if authoritative
                        else "values match but decisive authority is absent",
                        evidence,
                    )
                )

        verdicts = {item.verdict for item in assessments}
        if CompatibilityVerdict.INCOMPATIBLE in verdicts:
            overall = CompatibilityVerdict.INCOMPATIBLE
        elif assessments and verdicts == {CompatibilityVerdict.COMPATIBLE}:
            overall = CompatibilityVerdict.COMPATIBLE
        else:
            overall = CompatibilityVerdict.UNKNOWN
        return CompatibilityAssessment(
            producer.subject_id,
            consumer.subject_id,
            requirements.purpose,
            overall,
            tuple(assessments),
        )
