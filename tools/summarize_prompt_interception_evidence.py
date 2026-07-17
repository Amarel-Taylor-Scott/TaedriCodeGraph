#!/usr/bin/env python3
"""Summarize sanitized prompt-interception campaign receipts without re-running them.

The source campaign JSON remains the evidence of record.  This tool computes a
deterministic, compact index over those files: raw-file digests, campaign IDs,
provider-native token observations, checked-pack executions, and every failed
or rejected arm.  It deliberately does not promote observations into a
``token_savings`` claim.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from taedri_codegraph.prompt_interception import (
    PromptInterceptionError,
    validate_prompt_interception_campaign_document,
)

SUMMARY_FORMAT_VERSION = "2.0.0"
INPUT_TO_DISPLAY_CONDITION = {
    "full_catalog": "all_descriptions",
    "deterministic_shortlist": "locally_selected_descriptions",
}


class EvidenceSummaryError(ValueError):
    """Raised when campaign evidence is missing required structure."""


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceSummaryError(f"{label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceSummaryError(f"{label} must be an array")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceSummaryError(f"{label} must be a non-empty string")
    return value


def _require_nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceSummaryError(f"{label} must be a non-negative integer")
    return value


def _identity_id(value: object, label: str) -> str:
    identity = _require_mapping(value, label)
    return _require_text(identity.get("id"), f"{label}.id")


def _usage_totals(usages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    receipt_count = 0
    prompt_tokens = 0
    completion_tokens = 0
    wall_ms = 0
    usage_sources: set[str] = set()
    receipt_ids: set[str] = set()
    for usage in usages:
        receipt_count += 1
        prompt_tokens += _require_nonnegative_int(
            usage.get("prompt_tokens"), "model_usage.prompt_tokens"
        )
        completion_tokens += _require_nonnegative_int(
            usage.get("completion_tokens"), "model_usage.completion_tokens"
        )
        current_wall = usage.get("wall_ms")
        if current_wall is not None:
            wall_ms += _require_nonnegative_int(current_wall, "model_usage.wall_ms")
        source = usage.get("usage_source")
        if isinstance(source, str) and source:
            usage_sources.add(source)
        identity = usage.get("identity")
        if isinstance(identity, Mapping) and isinstance(identity.get("id"), str):
            receipt_ids.add(identity["id"])
    return {
        "receipt_count": receipt_count,
        "unique_receipt_count": len(receipt_ids),
        "usage_sources": sorted(usage_sources),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "wall_ms": wall_ms,
    }


def _ppm_toward_zero(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    magnitude = abs(numerator) * 1_000_000 // abs(denominator)
    return -magnitude if (numerator < 0) != (denominator < 0) else magnitude


def _arm_usage(arm: Mapping[str, Any]) -> Mapping[str, Any] | None:
    interception = arm.get("interception")
    if not isinstance(interception, Mapping):
        return None
    usage = interception.get("model_usage")
    return usage if isinstance(usage, Mapping) else None


def _verification_counts(arms: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    receipts = 0
    accepted_receipts = 0
    executed_cases = 0
    passed_cases = 0
    checked_tcgpack_receipts = 0
    for arm in arms:
        verification = arm.get("verification")
        if not isinstance(verification, Mapping):
            continue
        receipts += 1
        accepted_receipts += int(verification.get("accepted") is True)
        executed = _require_nonnegative_int(
            verification.get("executed_case_count", 0),
            "verification.executed_case_count",
        )
        passed = _require_nonnegative_int(
            verification.get("passed_case_count", 0),
            "verification.passed_case_count",
        )
        if passed > executed:
            raise EvidenceSummaryError(
                "verification.passed_case_count exceeds executed_case_count"
            )
        executed_cases += executed
        passed_cases += passed
        handle = verification.get("artifact_handle")
        if isinstance(handle, Mapping):
            location = handle.get("location")
            if (
                handle.get("scope") == "checked_primitive_catalog"
                and isinstance(location, str)
                and location.endswith(".tcgpack")
                and executed > 0
            ):
                checked_tcgpack_receipts += 1
    return {
        "verification_receipt_count": receipts,
        "accepted_verification_receipt_count": accepted_receipts,
        "executed_case_count": executed_cases,
        "passed_case_count": passed_cases,
        "failed_case_count": executed_cases - passed_cases,
        "checked_tcgpack_execution_receipt_count": checked_tcgpack_receipts,
    }


def summarize_campaign(path: Path) -> dict[str, Any]:
    """Return a deterministic summary of one sanitized campaign JSON file."""

    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceSummaryError(f"invalid campaign JSON: {path}") from exc
    campaign = _require_mapping(document, str(path))
    try:
        validation = validate_prompt_interception_campaign_document(campaign)
    except PromptInterceptionError as exc:
        raise EvidenceSummaryError(
            f"campaign failed strict receipt validation: {path}: {exc}"
        ) from exc
    arms_raw = _require_list(campaign.get("arms"), "campaign.arms")
    pairs_raw = _require_list(campaign.get("matched_pairs"), "campaign.matched_pairs")
    arms = [_require_mapping(item, "campaign.arms[]") for item in arms_raw]
    pairs = [_require_mapping(item, "campaign.matched_pairs[]") for item in pairs_raw]

    campaign_id = _identity_id(campaign.get("identity"), "campaign.identity")
    provider_id = _require_text(campaign.get("provider_id"), "campaign.provider_id")
    model_requested = _require_text(
        campaign.get("model_requested"), "campaign.model_requested"
    )
    maximum_locally_selected_descriptions = _require_nonnegative_int(
        campaign.get("shortlist_limit"), "campaign.shortlist_limit"
    )

    by_condition: dict[str, dict[str, Any]] = {}
    for input_name, display_name in INPUT_TO_DISPLAY_CONDITION.items():
        selected = [arm for arm in arms if arm.get("retrieval_arm") == input_name]
        usages = [usage for arm in selected if (usage := _arm_usage(arm)) is not None]
        candidate_counts = []
        for arm in selected:
            interception = arm.get("interception")
            candidates = (
                interception.get("candidates")
                if isinstance(interception, Mapping)
                else None
            )
            if isinstance(candidates, list):
                candidate_counts.append(len(candidates))
        by_condition[display_name] = {
            "call_count": len(selected),
            "accepted_call_count": sum(
                arm.get("status") == "accepted" for arm in selected
            ),
            "status_counts": dict(
                sorted(Counter(str(arm.get("status")) for arm in selected).items())
            ),
            "candidate_description_counts": {
                "receipt_count": len(candidate_counts),
                "minimum": min(candidate_counts) if candidate_counts else None,
                "maximum": max(candidate_counts) if candidate_counts else None,
                "distribution": {
                    str(count): frequency
                    for count, frequency in sorted(Counter(candidate_counts).items())
                },
            },
            "provider_native_usage": _usage_totals(usages),
            "verification": _verification_counts(selected),
        }

    failures: list[dict[str, Any]] = []
    for arm in arms:
        status = arm.get("status")
        error_code = arm.get("error_code")
        if status == "accepted" and error_code is None:
            continue
        input_condition = arm.get("retrieval_arm")
        if input_condition not in INPUT_TO_DISPLAY_CONDITION:
            raise EvidenceSummaryError(
                f"unsupported campaign retrieval condition: {input_condition!r}"
            )
        failures.append(
            {
                "call_receipt_id": _identity_id(
                    arm.get("identity"), "campaign.arms[].identity"
                ),
                "task_id": arm.get("task_id"),
                "trajectory_id": arm.get("trajectory_id"),
                "step_index": arm.get("step_index"),
                "seed": arm.get("seed"),
                "attempt_index": arm.get("attempt_index"),
                "condition": INPUT_TO_DISPLAY_CONDITION[input_condition],
                "status": status,
                "error_code": error_code,
            }
        )
    failures.sort(
        key=lambda item: (
            str(item["task_id"]),
            str(item["condition"]),
            int(item["seed"] or 0),
            int(item["attempt_index"] or 0),
        )
    )

    pair_ids = [
        _identity_id(pair.get("identity"), "campaign.matched_pairs[].identity")
        for pair in pairs
    ]
    if len(pair_ids) != len(set(pair_ids)):
        raise EvidenceSummaryError("campaign contains duplicate matched-pair IDs")
    comparable_pairs = [
        pair
        for pair in pairs
        if isinstance(pair.get("full_catalog_usage"), Mapping)
        and isinstance(pair.get("shortlist_usage"), Mapping)
    ]
    matched_full_usage = _usage_totals(
        _require_mapping(pair["full_catalog_usage"], "pair.full_catalog_usage")
        for pair in comparable_pairs
    )
    matched_locally_selected_usage = _usage_totals(
        _require_mapping(pair["shortlist_usage"], "pair.shortlist_usage")
        for pair in comparable_pairs
    )
    comparison_available = bool(comparable_pairs)
    prompt_delta = (
        matched_full_usage["prompt_tokens"]
        - matched_locally_selected_usage["prompt_tokens"]
    )
    completion_delta = (
        matched_full_usage["completion_tokens"]
        - matched_locally_selected_usage["completion_tokens"]
    )
    total_delta = (
        matched_full_usage["total_tokens"]
        - matched_locally_selected_usage["total_tokens"]
    )

    status_counts = Counter(str(arm.get("status")) for arm in arms)
    error_counts = Counter(
        str(arm.get("error_code"))
        for arm in arms
        if arm.get("error_code") is not None
    )
    task_ids = sorted(
        {str(arm.get("task_id")) for arm in arms if arm.get("task_id") is not None}
    )
    seeds = campaign.get("seeds")
    if not isinstance(seeds, list):
        raise EvidenceSummaryError("campaign.seeds must be an array")

    all_verification = _verification_counts(arms)
    return {
        "campaign_file": path.name,
        "campaign_file_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        "campaign_file_bytes": len(raw),
        "campaign_id": campaign_id,
        "source_format_version": validation.format_version,
        "strict_validation": validation.to_dict(),
        "provider_id": provider_id,
        "model_requested": model_requested,
        "maximum_locally_selected_descriptions": (
            maximum_locally_selected_descriptions
        ),
        "seeds": seeds,
        "catalog_digest": campaign.get("catalog_digest"),
        "task_set_digest": campaign.get("task_set_digest"),
        "task_count": validation.task_count,
        "task_ids": task_ids,
        "condition_call_count": len(arms),
        "matched_condition_pair_count": len(pairs),
        "provider_usage_comparable_pair_count": len(comparable_pairs),
        "both_conditions_accepted_pair_count": sum(
            pair.get("full_catalog_accepted") is True
            and pair.get("shortlist_accepted") is True
            for pair in pairs
        ),
        "all_descriptions_accepted_pair_count": sum(
            pair.get("full_catalog_accepted") is True for pair in pairs
        ),
        "locally_selected_descriptions_accepted_pair_count": sum(
            pair.get("shortlist_accepted") is True for pair in pairs
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "error_code_counts": dict(sorted(error_counts.items())),
        "failure_count": len(failures),
        "failures": failures,
        "by_condition": by_condition,
        "verification": all_verification,
        "provider_native_token_observation": {
            "comparison_available": comparison_available,
            "all_descriptions_total_tokens": matched_full_usage["total_tokens"],
            "locally_selected_descriptions_total_tokens": matched_locally_selected_usage[
                "total_tokens"
            ],
            "observed_delta_tokens": total_delta if comparison_available else None,
            "observed_delta_ppm_of_all_descriptions": (
                _ppm_toward_zero(total_delta, matched_full_usage["total_tokens"])
                if comparison_available
                else None
            ),
            "all_descriptions_prompt_tokens": matched_full_usage["prompt_tokens"],
            "locally_selected_descriptions_prompt_tokens": matched_locally_selected_usage[
                "prompt_tokens"
            ],
            "observed_prompt_delta_tokens": (
                prompt_delta if comparison_available else None
            ),
            "all_descriptions_completion_tokens": matched_full_usage[
                "completion_tokens"
            ],
            "locally_selected_descriptions_completion_tokens": matched_locally_selected_usage[
                "completion_tokens"
            ],
            "observed_completion_delta_tokens": (
                completion_delta if comparison_available else None
            ),
        },
    }


def build_summary(paths: Sequence[Path]) -> dict[str, Any]:
    if not paths:
        raise EvidenceSummaryError("at least one campaign file is required")
    campaigns = [summarize_campaign(path) for path in paths]
    campaigns.sort(
        key=lambda item: (
            item["provider_id"],
            item["model_requested"],
            item["maximum_locally_selected_descriptions"],
            item["campaign_file"],
        )
    )
    ids = [item["campaign_id"] for item in campaigns]
    if len(ids) != len(set(ids)):
        raise EvidenceSummaryError("input contains duplicate campaign IDs")

    totals = {
        "campaign_count": len(campaigns),
        "strict_v2_campaign_count": sum(
            not item["strict_validation"]["legacy"] for item in campaigns
        ),
        "legacy_nonclaimable_campaign_count": sum(
            item["strict_validation"]["legacy"] for item in campaigns
        ),
        "campaign_observation_task_count": sum(item["task_count"] for item in campaigns),
        "condition_call_count": sum(
            item["condition_call_count"] for item in campaigns
        ),
        "matched_condition_pair_count": sum(
            item["matched_condition_pair_count"] for item in campaigns
        ),
        "provider_usage_comparable_pair_count": sum(
            item["provider_usage_comparable_pair_count"] for item in campaigns
        ),
        "provider_usage_comparable_campaign_count": sum(
            item["provider_native_token_observation"]["comparison_available"]
            for item in campaigns
        ),
        "provider_usage_noncomparable_campaign_count": sum(
            not item["provider_native_token_observation"]["comparison_available"]
            for item in campaigns
        ),
        "token_totals_scope": (
            "only matched pairs with provider usage receipts for both conditions"
        ),
        "failure_count": sum(item["failure_count"] for item in campaigns),
        "executed_case_count": sum(
            item["verification"]["executed_case_count"] for item in campaigns
        ),
        "passed_case_count": sum(
            item["verification"]["passed_case_count"] for item in campaigns
        ),
        "failed_case_count": sum(
            item["verification"]["failed_case_count"] for item in campaigns
        ),
        "checked_tcgpack_execution_receipt_count": sum(
            item["verification"]["checked_tcgpack_execution_receipt_count"]
            for item in campaigns
        ),
        "all_descriptions_total_tokens": sum(
            item["provider_native_token_observation"]["all_descriptions_total_tokens"]
            for item in campaigns
        ),
        "locally_selected_descriptions_total_tokens": sum(
            item["provider_native_token_observation"][
                "locally_selected_descriptions_total_tokens"
            ]
            for item in campaigns
        ),
    }
    totals["observed_delta_tokens"] = (
        totals["all_descriptions_total_tokens"]
        - totals["locally_selected_descriptions_total_tokens"]
    )
    totals["observed_delta_ppm_of_all_descriptions"] = _ppm_toward_zero(
        totals["observed_delta_tokens"], totals["all_descriptions_total_tokens"]
    )
    return {
        "format_version": SUMMARY_FORMAT_VERSION,
        "classification": "provider_native_observation_only",
        "claimable_token_savings": False,
        "claim_gate": (
            "A separate token_savings integrity evaluation with its trusted "
            "evidence resolver must decide claimability; legacy campaigns cannot "
            "supply independent-execution occurrence evidence."
        ),
        "scope": {
            "cohort": "constructed_in_catalog_natural_tasks",
            "execution": "actual_checked_tcgpack_execution",
            "verification_cases": (
                "hidden from model calls; public fixture; not cryptographically sealed"
            ),
            "production_status": "not_organic_production_traffic",
            "token_source": "provider_native_receipts",
            "measurement_stage": (
                "selector_and_context_stage_only_not_complete_coding_session"
            ),
            "intervention": (
                "deterministic local retrieval plus reduced and rank-reordered "
                "primitive-card disclosure; candidate route handles are scoped "
                "to the disclosed order"
            ),
        },
        "campaigns": campaigns,
        "campaign_observation_totals": totals,
    }


CSV_FIELDS = (
    "campaign_file",
    "campaign_file_sha256",
    "campaign_id",
    "provider_id",
    "model_requested",
    "maximum_locally_selected_descriptions",
    "seeds",
    "task_count",
    "condition_call_count",
    "matched_condition_pair_count",
    "provider_usage_comparable_pair_count",
    "token_comparison_available",
    "both_conditions_accepted_pair_count",
    "all_descriptions_accepted_call_count",
    "locally_selected_descriptions_accepted_call_count",
    "all_descriptions_candidate_count_minimum",
    "all_descriptions_candidate_count_maximum",
    "locally_selected_descriptions_candidate_count_minimum",
    "locally_selected_descriptions_candidate_count_maximum",
    "failure_count",
    "failure_codes",
    "provider_usage_sources",
    "all_descriptions_prompt_tokens",
    "all_descriptions_completion_tokens",
    "all_descriptions_total_tokens",
    "locally_selected_descriptions_prompt_tokens",
    "locally_selected_descriptions_completion_tokens",
    "locally_selected_descriptions_total_tokens",
    "observed_delta_tokens",
    "observed_delta_ppm_of_all_descriptions",
    "executed_case_count",
    "passed_case_count",
    "failed_case_count",
    "checked_tcgpack_execution_receipt_count",
)


def csv_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for campaign in summary["campaigns"]:
        all_descriptions = campaign["by_condition"]["all_descriptions"]
        locally_selected = campaign["by_condition"][
            "locally_selected_descriptions"
        ]
        all_usage = all_descriptions["provider_native_usage"]
        locally_selected_usage = locally_selected["provider_native_usage"]
        observation = campaign["provider_native_token_observation"]
        usage_sources = sorted(
            set(all_usage["usage_sources"])
            | set(locally_selected_usage["usage_sources"])
        )
        rows.append(
            {
                "campaign_file": campaign["campaign_file"],
                "campaign_file_sha256": campaign["campaign_file_sha256"],
                "campaign_id": campaign["campaign_id"],
                "provider_id": campaign["provider_id"],
                "model_requested": campaign["model_requested"],
                "maximum_locally_selected_descriptions": campaign[
                    "maximum_locally_selected_descriptions"
                ],
                "seeds": ";".join(str(seed) for seed in campaign["seeds"]),
                "task_count": campaign["task_count"],
                "condition_call_count": campaign["condition_call_count"],
                "matched_condition_pair_count": campaign[
                    "matched_condition_pair_count"
                ],
                "provider_usage_comparable_pair_count": campaign[
                    "provider_usage_comparable_pair_count"
                ],
                "token_comparison_available": observation["comparison_available"],
                "both_conditions_accepted_pair_count": campaign[
                    "both_conditions_accepted_pair_count"
                ],
                "all_descriptions_accepted_call_count": all_descriptions[
                    "accepted_call_count"
                ],
                "locally_selected_descriptions_accepted_call_count": locally_selected[
                    "accepted_call_count"
                ],
                "all_descriptions_candidate_count_minimum": all_descriptions[
                    "candidate_description_counts"
                ]["minimum"],
                "all_descriptions_candidate_count_maximum": all_descriptions[
                    "candidate_description_counts"
                ]["maximum"],
                "locally_selected_descriptions_candidate_count_minimum": locally_selected[
                    "candidate_description_counts"
                ]["minimum"],
                "locally_selected_descriptions_candidate_count_maximum": locally_selected[
                    "candidate_description_counts"
                ]["maximum"],
                "failure_count": campaign["failure_count"],
                "failure_codes": ";".join(campaign["error_code_counts"]),
                "provider_usage_sources": ";".join(usage_sources),
                "all_descriptions_prompt_tokens": observation[
                    "all_descriptions_prompt_tokens"
                ],
                "all_descriptions_completion_tokens": observation[
                    "all_descriptions_completion_tokens"
                ],
                "all_descriptions_total_tokens": observation[
                    "all_descriptions_total_tokens"
                ],
                "locally_selected_descriptions_prompt_tokens": observation[
                    "locally_selected_descriptions_prompt_tokens"
                ],
                "locally_selected_descriptions_completion_tokens": observation[
                    "locally_selected_descriptions_completion_tokens"
                ],
                "locally_selected_descriptions_total_tokens": observation[
                    "locally_selected_descriptions_total_tokens"
                ],
                "observed_delta_tokens": observation["observed_delta_tokens"],
                "observed_delta_ppm_of_all_descriptions": observation[
                    "observed_delta_ppm_of_all_descriptions"
                ],
                "executed_case_count": campaign["verification"][
                    "executed_case_count"
                ],
                "passed_case_count": campaign["verification"]["passed_case_count"],
                "failed_case_count": campaign["verification"]["failed_case_count"],
                "checked_tcgpack_execution_receipt_count": campaign["verification"][
                    "checked_tcgpack_execution_receipt_count"
                ],
            }
        )
    return rows


def write_summary_outputs(
    summary: Mapping[str, Any], summary_path: Path, csv_path: Path
) -> None:
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows(summary))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize existing sanitized prompt-interception campaigns."
    )
    parser.add_argument("campaign", nargs="+", type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        summary = build_summary(args.campaign)
        write_summary_outputs(summary, args.summary, args.csv)
    except (EvidenceSummaryError, OSError) as exc:
        parser.exit(2, f"evidence summary rejected: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
