"""AST-only factory for registry-native primitive candidates from real Python code.

The factory never imports or executes the analyzed tree.  It packages source-backed
function and method fragments, candidate contracts, graph neighborhoods, and search
descriptors.  Every output remains an intake candidate; syntax inference is not a
behavioral verification claim.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .canonical import canonical_digest, canonical_json_bytes, sha256_digest
from .contracts import ProducerRef, RecordMixin
from .identity import IdentityRecord
from .intake import (
    CandidateIntakeLedger,
    CandidateOrigin,
    CandidateState,
    CandidateSubmission,
    CandidateVisibility,
    LicenseEvidenceState,
)
from .primitive_capsules import (
    CapsuleRole,
    PrimitiveHandle,
    PrimitiveRegistry,
    PrimitiveTreeEntry,
    RefKind,
)

_NON_HANDLE = re.compile(r"[^a-z0-9._-]+")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_SKIP_DIRECTORIES = frozenset(
    {".git", ".hg", ".mypy_cache", ".pytest_cache", ".tox", ".venv", "__pycache__", "build", "dist"}
)


class PrimitiveFactoryError(ValueError):
    """Raised when a factory configuration cannot produce bounded candidates."""


@dataclass(frozen=True, slots=True)
class PrimitiveFactoryDiagnostic(RecordMixin):
    source_path: str
    diagnostic_kind: str
    message: str
    line: int | None
    column: int | None


@dataclass(frozen=True, slots=True)
class FunctionPrimitiveCandidate(RecordMixin):
    identity: IdentityRecord
    primitive: PrimitiveHandle
    revision_id: str
    tree_id: str
    submission_id: str | None
    intake_state: str
    source_path: str
    module: str
    qualified_name: str
    entity_kind: str
    start_line: int
    end_line: int
    positional_arity: int
    call_labels: tuple[str, ...]
    lexical_tokens: tuple[str, ...]
    doc_summary: str | None
    original_file_digest: str
    fragment_digest: str
    contract_digest: str
    descriptor_digest: str
    graph_digest: str
    generation_run_id: str


@dataclass(frozen=True, slots=True)
class PrimitiveFactoryResult(RecordMixin):
    identity: IdentityRecord
    format_version: str
    generation_run_id: str
    source_root: str
    source_uri: str
    source_revision: str | None
    root_digest: str
    package_name: str
    namespace: str
    created_at: str
    source_file_count: int
    scanned_source_bytes: int
    unique_blob_count: int
    unique_blob_bytes: int
    candidates: tuple[FunctionPrimitiveCandidate, ...]
    diagnostics: tuple[PrimitiveFactoryDiagnostic, ...]

    def summary(self) -> dict[str, object]:
        kind_counts: dict[str, int] = {}
        for candidate in self.candidates:
            kind_counts[candidate.entity_kind] = kind_counts.get(candidate.entity_kind, 0) + 1
        return {
            "factory_run_id": self.identity.id,
            "generation_run_id": self.generation_run_id,
            "root_digest": self.root_digest,
            "source_files": self.source_file_count,
            "scanned_source_bytes": self.scanned_source_bytes,
            "candidate_count": len(self.candidates),
            "candidate_kinds": dict(sorted(kind_counts.items())),
            "call_edge_count": sum(len(item.call_labels) for item in self.candidates),
            "diagnostic_count": len(self.diagnostics),
            "unique_blob_count": self.unique_blob_count,
            "unique_blob_bytes": self.unique_blob_bytes,
            "intake_states": sorted({item.intake_state for item in self.candidates}),
        }


@dataclass(frozen=True, slots=True)
class _DiscoveredFunction:
    node: ast.FunctionDef | ast.AsyncFunctionDef
    qualified_name: str
    entity_kind: str


class _FunctionCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[tuple[str, str]] = []
        self.functions: list[_DiscoveredFunction] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.stack.append((node.name, "class"))
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node, asynchronous=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node, asynchronous=True)

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, asynchronous: bool
    ) -> None:
        parent_kind = self.stack[-1][1] if self.stack else None
        if parent_kind == "class":
            kind = "async_method" if asynchronous else "method"
        elif self.stack:
            kind = "async_nested_function" if asynchronous else "nested_function"
        else:
            kind = "async_function" if asynchronous else "function"
        qualified_name = ".".join([*(name for name, _ in self.stack), node.name])
        self.functions.append(_DiscoveredFunction(node, qualified_name, kind))
        self.stack.append((node.name, "function"))
        self.generic_visit(node)
        self.stack.pop()


class _DirectCallCollector(ast.NodeVisitor):
    """Collect calls in one body without attributing nested definitions to it."""

    def __init__(self) -> None:
        self.labels: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self.labels.add(_call_label(node.func))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        return


class PrimitiveFactory:
    """Create immutable primitive revisions and optional intake events from source."""

    def generate(
        self,
        root: str | Path,
        *,
        registry: PrimitiveRegistry,
        producer: ProducerRef,
        package_name: str,
        namespace: str,
        source_uri: str,
        created_at: str,
        source_revision: str | None = None,
        license_expression: str | None = None,
        license_evidence_state: LicenseEvidenceState = LicenseEvidenceState.UNKNOWN,
        visibility: CandidateVisibility = CandidateVisibility.PRIVATE,
        intake: CandidateIntakeLedger | None = None,
        max_candidates: int = 1000,
    ) -> PrimitiveFactoryResult:
        if not 1 <= max_candidates <= 100_000:
            raise PrimitiveFactoryError("max_candidates must be between 1 and 100000")
        source_root = Path(root).resolve()
        if not source_root.is_dir():
            raise PrimitiveFactoryError(f"source root is not a directory: {source_root}")
        normalized_namespace = _handle_part(namespace)
        files = tuple(self._source_files(source_root))
        file_payloads = [(path, path.read_bytes()) for path in files]
        root_digest = canonical_digest(
            [
                {
                    "path": path.relative_to(source_root).as_posix(),
                    "content_digest": sha256_digest(content),
                }
                for path, content in file_payloads
            ]
        )
        generation_run_id = IdentityRecord.create(
            "generation_run",
            {
                "producer": producer.to_dict(),
                "source_uri": source_uri,
                "source_revision": source_revision,
                "root_digest": root_digest,
                "package_name": package_name,
                "namespace": normalized_namespace,
                "factory_contract": "python-function-candidates-v1",
                "created_at": created_at,
                "max_candidates": max_candidates,
            },
        ).id
        candidates: list[FunctionPrimitiveCandidate] = []
        diagnostics: list[PrimitiveFactoryDiagnostic] = []
        for path, content in file_payloads:
            relative_path = path.relative_to(source_root).as_posix()
            try:
                text = _decode_python(content)
                tree = ast.parse(text, filename=relative_path, type_comments=True)
            except (SyntaxError, UnicodeError, LookupError) as exc:
                diagnostics.append(
                    PrimitiveFactoryDiagnostic(
                        relative_path,
                        type(exc).__name__,
                        str(exc),
                        getattr(exc, "lineno", None),
                        getattr(exc, "offset", None),
                    )
                )
                continue
            module = _module_name(package_name, Path(relative_path))
            collector = _FunctionCollector()
            collector.visit(tree)
            original_blob = registry.put_blob(content, "text/x-python")
            for discovered in collector.functions:
                if len(candidates) >= max_candidates:
                    diagnostics.append(
                        PrimitiveFactoryDiagnostic(
                            relative_path,
                            "candidate_limit_reached",
                            f"generation stopped at the configured limit of {max_candidates}",
                            discovered.node.lineno,
                            discovered.node.col_offset,
                        )
                    )
                    break
                candidates.append(
                    self._package_function(
                        registry=registry,
                        intake=intake,
                        producer=producer,
                        namespace=normalized_namespace,
                        source_uri=source_uri,
                        source_revision=source_revision,
                        created_at=created_at,
                        generation_run_id=generation_run_id,
                        license_expression=license_expression,
                        license_evidence_state=license_evidence_state,
                        visibility=visibility,
                        relative_path=relative_path,
                        original_blob_digest=original_blob.digest,
                        text=text,
                        module=module,
                        discovered=discovered,
                    )
                )
            if len(candidates) >= max_candidates:
                break
        result_key = {
            "format_version": "1.0.0",
            "generation_run_id": generation_run_id,
            "root_digest": root_digest,
            "candidate_ids": [candidate.identity.id for candidate in candidates],
            "diagnostics": [diagnostic.to_dict() for diagnostic in diagnostics],
        }
        return PrimitiveFactoryResult(
            IdentityRecord.create("primitive_factory_result", result_key),
            "1.0.0",
            generation_run_id,
            source_root.as_posix(),
            source_uri,
            source_revision,
            root_digest,
            package_name,
            normalized_namespace,
            created_at,
            len(files),
            sum(len(content) for _, content in file_payloads),
            len(registry.blobs),
            sum(len(content) for content in registry.blobs.values()),
            tuple(candidates),
            tuple(diagnostics),
        )

    def _package_function(
        self,
        *,
        registry: PrimitiveRegistry,
        intake: CandidateIntakeLedger | None,
        producer: ProducerRef,
        namespace: str,
        source_uri: str,
        source_revision: str | None,
        created_at: str,
        generation_run_id: str,
        license_expression: str | None,
        license_evidence_state: LicenseEvidenceState,
        visibility: CandidateVisibility,
        relative_path: str,
        original_blob_digest: str,
        text: str,
        module: str,
        discovered: _DiscoveredFunction,
    ) -> FunctionPrimitiveCandidate:
        node = discovered.node
        fragment = ast.get_source_segment(text, node)
        if fragment is None:  # pragma: no cover - ast normally provides positions
            fragment = "\n".join(text.splitlines()[node.lineno - 1 : node.end_lineno])
        fragment_bytes = (fragment.rstrip() + "\n").encode("utf-8")
        parameters = _parameters(node.args)
        returns = _annotation(node.returns)
        call_collector = _DirectCallCollector()
        for statement in node.body:
            call_collector.visit(statement)
        calls = tuple(sorted(call_collector.labels))
        decorators = tuple(sorted(filter(None, (_expression_label(item) for item in node.decorator_list))))
        docstring = ast.get_docstring(node, clean=True)
        doc_summary = _doc_summary(docstring)
        lexical_tokens = _lexical_tokens(
            module, discovered.qualified_name, *(calls or ()), doc_summary or ""
        )
        positional_arity = len(node.args.posonlyargs) + len(node.args.args)
        symbol_key = f"{module}:{discovered.qualified_name}"
        contract_data = {
            "schema_version": "1.0.0",
            "evidence_class": "syntax-derived-candidate-not-behaviorally-verified",
            "subject": {
                "qualified_name": symbol_key,
                "entity_kind": discovered.entity_kind,
                "async": isinstance(node, ast.AsyncFunctionDef),
            },
            "inputs": parameters,
            "output": {"annotation": returns, "state": "extracted" if returns else "unknown"},
            "decorators": decorators,
            "effects": {"state": "unknown", "reason": "source was not executed"},
            "exceptions": {"state": "unknown", "reason": "no control-flow proof was run"},
            "source_selection": {
                "path": relative_path,
                "start_line": node.lineno,
                "end_line": node.end_lineno,
                "original_file_digest": original_blob_digest,
                "utf8_fragment_digest": sha256_digest(fragment_bytes),
            },
            "license": {
                "expression": license_expression,
                "evidence_state": license_evidence_state.value,
            },
        }
        descriptor_data = {
            "schema_version": "1.0.0",
            "evidence_class": "search-assisting-candidate",
            "subject": symbol_key,
            "display_name": node.name,
            "qualified_name": discovered.qualified_name,
            "module": module,
            "entity_kind": discovered.entity_kind,
            "aliases": sorted({node.name, discovered.qualified_name, symbol_key}),
            "lexical_tokens": lexical_tokens,
            "keyphrases": [doc_summary] if doc_summary else [],
            "call_labels": calls,
            "blocking_keys": [
                f"kind:{discovered.entity_kind}",
                f"arity:{positional_arity}",
                f"module:{module}",
                f"return:{returns or 'unknown'}",
            ],
            "multiresolution_lsh_inputs": {
                "narrow": [symbol_key, decorators, parameters, returns, calls],
                "medium": [discovered.entity_kind, positional_arity, lexical_tokens, calls],
                "wide": [discovered.entity_kind, lexical_tokens],
            },
            "search_text": " ".join(
                filter(None, (symbol_key, doc_summary or "", " ".join(calls), " ".join(lexical_tokens)))
            ),
            "embedding_projections": {
                "status": "not_attempted",
                "recommended_channels": ["source", "documentation", "contract", "graph_neighborhood"],
                "enrichment_rule": "materialize only after ambiguity or measured marginal retrieval value",
            },
            "disclosure_depth": "D2-signature-contract-and-neighborhood",
        }
        graph_data = {
            "schema_version": "1.0.0",
            "evidence_class": "syntax-extracted-call-candidates",
            "subject": symbol_key,
            "edges": [
                {
                    "source": symbol_key,
                    "predicate": "uceg.predicate.calls_may",
                    "target_label": target,
                    "modality": "extracted",
                    "verification_state": "unverified",
                }
                for target in calls
            ],
        }
        fragment_blob = registry.put_blob(fragment_bytes, "text/x-python")
        contract_blob = registry.put_blob(
            canonical_json_bytes(contract_data),
            "application/vnd.taedri.primitive.contract.v1+json",
        )
        descriptor_blob = registry.put_blob(
            canonical_json_bytes(descriptor_data),
            "application/vnd.taedri.primitive.descriptor.v1+json",
        )
        graph_blob = registry.put_blob(
            canonical_json_bytes(graph_data),
            "application/vnd.taedri.codegraph.edges.v1+json",
        )
        original_blob = registry.blob_descriptors[original_blob_digest]
        entries = [
            PrimitiveTreeEntry(
                f"source/original/{relative_path}", CapsuleRole.SOURCE, original_blob
            ),
            PrimitiveTreeEntry("source/fragment.py", CapsuleRole.SOURCE, fragment_blob),
            PrimitiveTreeEntry("contract.json", CapsuleRole.CONTRACT, contract_blob),
            PrimitiveTreeEntry("search/descriptor.json", CapsuleRole.DESCRIPTOR, descriptor_blob),
            PrimitiveTreeEntry("graph/neighborhood.json", CapsuleRole.GRAPH_DELTA, graph_blob),
        ]
        if docstring:
            documentation = registry.put_blob(
                (f"# {symbol_key}\n\n{docstring.strip()}\n").encode("utf-8"),
                "text/markdown",
            )
            entries.append(
                PrimitiveTreeEntry(
                    "documentation/docstring.md", CapsuleRole.DOCUMENTATION, documentation
                )
            )
        tree = registry.create_tree(entries)
        handle_name = _primitive_name(relative_path, module, discovered.qualified_name, node.lineno)
        handle = registry.register_handle(namespace, handle_name)
        revision = registry.commit(
            primitive=handle,
            tree_id=tree.identity.id,
            contract_digest=contract_blob.digest,
            producer=producer,
            author=producer.id,
            created_at=created_at,
            message=f"Extract syntax-backed candidate {symbol_key}",
            generation_run_id=generation_run_id,
            evidence_ids=(original_blob_digest, fragment_blob.digest),
        )
        registry.update_ref(
            primitive=handle,
            ref_kind=RefKind.BRANCH,
            ref_name="candidate",
            new_revision_id=revision.identity.id,
            expected_revision_id=None,
            actor=producer.id,
            updated_at=created_at,
        )
        submission_id: str | None = None
        intake_state = "capsule_candidate"
        if intake is not None:
            submission = CandidateSubmission.create(
                primitive_id=handle.identity.id,
                revision_id=revision.identity.id,
                origin=CandidateOrigin.EXTRACTED,
                producer=producer,
                submitted_by=producer.id,
                submitted_at=created_at,
                source_uri=source_uri,
                source_revision=source_revision,
                license_expression=license_expression,
                license_evidence_state=license_evidence_state,
                visibility=visibility,
                production_run_id=generation_run_id,
                evidence_ids=(original_blob_digest, fragment_blob.digest),
            )
            intake.submit(submission)
            intake.transition(
                submission.identity.id,
                CandidateState.QUARANTINED,
                actor=producer.id,
                occurred_at=created_at,
                reason="target source remained unexecuted during AST-only extraction",
                evidence_ids=(original_blob_digest,),
            )
            intake.transition(
                submission.identity.id,
                CandidateState.STRUCTURALLY_VALID,
                actor=producer.id,
                occurred_at=created_at,
                reason="capsule tree, digests, contract binding, and AST locations validated",
                evidence_ids=(tree.identity.id, revision.identity.id),
            )
            intake.transition(
                submission.identity.id,
                CandidateState.INDEXED_CANDIDATE,
                actor=producer.id,
                occurred_at=created_at,
                reason="exact, lexical, blocking, and multi-resolution LSH inputs are available",
                evidence_ids=(descriptor_blob.digest,),
            )
            submission_id = submission.identity.id
            intake_state = CandidateState.INDEXED_CANDIDATE.value
        candidate_key = {
            "primitive_id": handle.identity.id,
            "revision_id": revision.identity.id,
            "descriptor_digest": descriptor_blob.digest,
            "generation_run_id": generation_run_id,
        }
        return FunctionPrimitiveCandidate(
            IdentityRecord.create("function_primitive_candidate", candidate_key),
            handle,
            revision.identity.id,
            tree.identity.id,
            submission_id,
            intake_state,
            relative_path,
            module,
            discovered.qualified_name,
            discovered.entity_kind,
            node.lineno,
            node.end_lineno or node.lineno,
            positional_arity,
            calls,
            lexical_tokens,
            doc_summary,
            original_blob_digest,
            fragment_blob.digest,
            contract_blob.digest,
            descriptor_blob.digest,
            graph_blob.digest,
            generation_run_id,
        )

    @staticmethod
    def _source_files(root: Path) -> Iterable[Path]:
        for path in sorted(root.rglob("*.py")):
            relative_parts = path.relative_to(root).parts
            if path.is_symlink() or any(part in _SKIP_DIRECTORIES for part in relative_parts):
                continue
            if path.is_file():
                yield path


def _decode_python(content: bytes) -> str:
    encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
    return content.decode(encoding)


def _module_name(package_name: str, relative_path: Path) -> str:
    parts = list(relative_path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(filter(None, [package_name, *parts]))


def _handle_part(value: str) -> str:
    normalized = _NON_HANDLE.sub("-", value.lower()).strip("._-") or "candidate"
    if len(normalized) > 63:
        suffix = sha256_digest(value.encode("utf-8"))[7:17]
        normalized = normalized[:52].rstrip("._-") + "-" + suffix
    return normalized


def _primitive_name(path: str, module: str, qualified_name: str, line: int) -> str:
    stable_key = f"{path}:{module}:{qualified_name}:{line}"
    suffix = sha256_digest(stable_key.encode("utf-8"))[7:17]
    readable = _handle_part(f"{module}.{qualified_name}").replace(".", "-")
    return f"{readable[:52].rstrip('._-')}-{suffix}"


def _annotation(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _parameters(arguments: ast.arguments) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    positional = [
        *((item, "positional_only") for item in arguments.posonlyargs),
        *((item, "positional_or_keyword") for item in arguments.args),
    ]
    default_start = len(positional) - len(arguments.defaults)
    for index, (argument, kind) in enumerate(positional):
        result.append(
            {
                "name": argument.arg,
                "kind": kind,
                "annotation": _annotation(argument.annotation),
                "has_default": index >= default_start,
            }
        )
    if arguments.vararg is not None:
        result.append(
            {
                "name": arguments.vararg.arg,
                "kind": "variadic_positional",
                "annotation": _annotation(arguments.vararg.annotation),
                "has_default": False,
            }
        )
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
        result.append(
            {
                "name": argument.arg,
                "kind": "keyword_only",
                "annotation": _annotation(argument.annotation),
                "has_default": default is not None,
            }
        )
    if arguments.kwarg is not None:
        result.append(
            {
                "name": arguments.kwarg.arg,
                "kind": "variadic_keyword",
                "annotation": _annotation(arguments.kwarg.annotation),
                "has_default": False,
            }
        )
    return result


def _expression_label(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _expression_label(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _expression_label(node.func)
    return None


def _call_label(node: ast.expr) -> str:
    return _expression_label(node) or "<dynamic-call>"


def _doc_summary(docstring: str | None) -> str | None:
    if not docstring:
        return None
    first_paragraph = docstring.strip().split("\n\n", 1)[0]
    collapsed = " ".join(first_paragraph.split())
    return collapsed[:237] + "..." if len(collapsed) > 240 else collapsed


def _lexical_tokens(*values: object) -> tuple[str, ...]:
    tokens: set[str] = set()
    for value in values:
        expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
        for token in _WORD.findall(expanded):
            for part in token.split("_"):
                normalized = part.lower()
                if normalized:
                    tokens.add(normalized)
    return tuple(sorted(tokens))
