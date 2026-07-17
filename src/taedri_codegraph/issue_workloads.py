"""Validated, source-bound workloads derived from external GitHub issues.

The source metadata is deliberately kept outside :class:`NaturalPrimitiveTask`.
Campaign prompts therefore receive only the bounded task request while evaluators
retain an immutable local snapshot of the evidence used to derive that request.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .canonical import canonical_json_bytes, sha256_digest
from .prompt_interception import (
    NaturalPrimitiveTask,
    PromptInterceptionError,
    load_natural_primitive_tasks,
)

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_WORKLOAD_KIND = "external_github_issue_derived_primitive_retrieval_positive_only"
_CASE_DERIVATION = "independent_manual_cases_v1"


class IssueWorkloadError(ValueError):
    """Raised when an issue-grounded workload fails closed validation."""


def normalize_source_text(value: str) -> str:
    """Normalize an archived source field without changing its wording."""

    if not isinstance(value, str):
        raise IssueWorkloadError("source text must be a string")
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(line.rstrip(" \t") for line in value.split("\n")).strip()


def normalized_issue_source_digest(
    *,
    repository: str,
    issue_number: int,
    issue_title: str,
    source_excerpt: str,
) -> str:
    """Digest the exact normalized issue fields retained in the fixture."""

    payload = {
        "repository": repository,
        "issue_number": issue_number,
        "issue_title": normalize_source_text(issue_title),
        "source_excerpt": normalize_source_text(source_excerpt),
    }
    return sha256_digest(canonical_json_bytes(payload))


@dataclass(frozen=True, slots=True)
class IssueSourceProvenance:
    repository: str
    issue_number: int
    issue_title: str
    issue_url: str
    accessed_on: str
    source_excerpt: str
    normalized_source_digest: str
    derivation_scope: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "IssueSourceProvenance":
        required = {
            "repository",
            "issue_number",
            "issue_title",
            "issue_url",
            "accessed_on",
            "source_excerpt",
            "normalized_source_digest",
            "derivation_scope",
        }
        if set(raw) != required:
            raise IssueWorkloadError("issue source provenance fields are incomplete")
        value = cls(
            _required_string(raw, "repository"),
            _required_integer(raw, "issue_number"),
            _required_string(raw, "issue_title", allow_outer_whitespace=True),
            _required_string(raw, "issue_url"),
            _required_string(raw, "accessed_on"),
            _required_string(raw, "source_excerpt"),
            _required_string(raw, "normalized_source_digest"),
            _required_string(raw, "derivation_scope"),
        )
        value.validate()
        return value

    def validate(self) -> None:
        if not _REPOSITORY.fullmatch(self.repository):
            raise IssueWorkloadError("GitHub repository name is invalid")
        if self.issue_number <= 0:
            raise IssueWorkloadError("GitHub issue number must be positive")
        expected_url = f"https://github.com/{self.repository}/issues/{self.issue_number}"
        if self.issue_url != expected_url:
            raise IssueWorkloadError("GitHub issue URL does not bind repository and number")
        if not self.issue_title.strip() or len(self.issue_title) > 512:
            raise IssueWorkloadError("GitHub issue title is invalid")
        try:
            parsed_access_date = date.fromisoformat(self.accessed_on)
        except ValueError as exc:
            raise IssueWorkloadError("GitHub issue access date is invalid") from exc
        if parsed_access_date.isoformat() != self.accessed_on:
            raise IssueWorkloadError("GitHub issue access date is not canonical")
        if normalize_source_text(self.source_excerpt) != self.source_excerpt:
            raise IssueWorkloadError("GitHub issue source excerpt is not normalized")
        if len(self.source_excerpt) < 20:
            raise IssueWorkloadError("GitHub issue source excerpt is too short")
        if len(self.derivation_scope.strip()) < 20:
            raise IssueWorkloadError("issue task derivation scope is incomplete")
        if not _DIGEST.fullmatch(self.normalized_source_digest):
            raise IssueWorkloadError("normalized GitHub issue source digest is invalid")
        observed = normalized_issue_source_digest(
            repository=self.repository,
            issue_number=self.issue_number,
            issue_title=self.issue_title,
            source_excerpt=self.source_excerpt,
        )
        if observed != self.normalized_source_digest:
            raise IssueWorkloadError("normalized GitHub issue source digest does not match")


@dataclass(frozen=True, slots=True)
class ExpectedPrimitive:
    namespace: str
    name: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ExpectedPrimitive":
        if set(raw) != {"namespace", "name"}:
            raise IssueWorkloadError("expected primitive fields are incomplete")
        value = cls(
            _required_string(raw, "namespace"),
            _required_string(raw, "name"),
        )
        if not re.fullmatch(r"[a-z][a-z0-9._-]*", value.namespace):
            raise IssueWorkloadError("expected primitive namespace is invalid")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", value.name):
            raise IssueWorkloadError("expected primitive name is invalid")
        return value


@dataclass(frozen=True, slots=True)
class IssueGroundedPrimitiveTask:
    task: NaturalPrimitiveTask
    expected_primitive: ExpectedPrimitive
    source: IssueSourceProvenance
    case_derivation: str


@dataclass(frozen=True, slots=True)
class IssueGroundedWorkload:
    description: str
    claim_limitations: tuple[str, ...]
    tasks: tuple[IssueGroundedPrimitiveTask, ...]

    @property
    def natural_tasks(self) -> tuple[NaturalPrimitiveTask, ...]:
        """Return the model/verifier contract without provenance metadata."""

        return tuple(item.task for item in self.tasks)


def load_issue_grounded_workload(path: str | Path) -> IssueGroundedWorkload:
    """Load a positive-only issue workload and validate its archived sources."""

    try:
        raw_value = json.loads(Path(path).expanduser().read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IssueWorkloadError("issue-grounded workload fixture is unavailable") from exc
    if not isinstance(raw_value, Mapping):
        raise IssueWorkloadError("issue-grounded workload must be an object")
    if raw_value.get("schema_version") != "1.0.0":
        raise IssueWorkloadError("issue-grounded workload version is invalid")
    if raw_value.get("workload_kind") != _WORKLOAD_KIND:
        raise IssueWorkloadError("issue-grounded workload kind is invalid")
    if raw_value.get("negative_oracle_support") != "not_represented_in_v1":
        raise IssueWorkloadError("issue-grounded workload negative-oracle status is missing")
    description = _required_string(raw_value, "description")
    limitations = raw_value.get("claim_limitations")
    if (
        not isinstance(limitations, list)
        or len(limitations) < 3
        or any(not isinstance(item, str) or len(item.strip()) < 10 for item in limitations)
        or len(set(limitations)) != len(limitations)
    ):
        raise IssueWorkloadError("issue-grounded workload limitations are incomplete")
    if not any("not a full coding benchmark" in item.lower() for item in limitations):
        raise IssueWorkloadError("issue-grounded workload must disclaim coding-benchmark scope")
    raw_tasks = raw_value.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise IssueWorkloadError("issue-grounded workload has no tasks")
    try:
        natural_tasks = load_natural_primitive_tasks(path)
    except PromptInterceptionError as exc:
        raise IssueWorkloadError("issue-grounded natural task contract is invalid") from exc
    if len(natural_tasks) != len(raw_tasks):
        raise IssueWorkloadError("issue-grounded task metadata count is inconsistent")

    tasks: list[IssueGroundedPrimitiveTask] = []
    for natural_task, raw_task in zip(natural_tasks, raw_tasks, strict=True):
        if not isinstance(raw_task, Mapping):
            raise IssueWorkloadError("issue-grounded task must be an object")
        raw_expected = raw_task.get("expected_primitive")
        raw_source = raw_task.get("source_provenance")
        if not isinstance(raw_expected, Mapping) or not isinstance(raw_source, Mapping):
            raise IssueWorkloadError("issue-grounded task metadata is incomplete")
        derivation = _required_string(raw_task, "case_derivation")
        if derivation != _CASE_DERIVATION:
            raise IssueWorkloadError("hidden-case derivation declaration is invalid")
        tasks.append(
            IssueGroundedPrimitiveTask(
                natural_task,
                ExpectedPrimitive.from_mapping(raw_expected),
                IssueSourceProvenance.from_mapping(raw_source),
                derivation,
            )
        )
    urls = [item.source.issue_url for item in tasks]
    if len(set(urls)) != len(urls):
        raise IssueWorkloadError("GitHub issue sources must be unique within the workload")
    return IssueGroundedWorkload(description, tuple(limitations), tuple(tasks))


def _required_string(
    raw: Mapping[str, Any], field: str, *, allow_outer_whitespace: bool = False
) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise IssueWorkloadError(f"{field} must be a non-empty string")
    if not allow_outer_whitespace and value != value.strip():
        raise IssueWorkloadError(f"{field} must not contain outer whitespace")
    return value


def _required_integer(raw: Mapping[str, Any], field: str) -> int:
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise IssueWorkloadError(f"{field} must be an integer")
    return value
