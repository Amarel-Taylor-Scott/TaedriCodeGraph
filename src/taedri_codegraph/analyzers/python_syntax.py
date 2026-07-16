"""Safe, deterministic Python syntax ingestion.

The analyzer reads bytes and uses the standard-library parser. It never imports,
installs, builds, or executes the target package.
"""

from __future__ import annotations

import ast
import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from ..canonical import canonical_digest, sha256_digest
from ..contracts import (
    AnalysisManifest,
    CompletenessState,
    CoverageLedger,
    EntityRecord,
    EvidenceLevel,
    EvidenceRecord,
    FeatureAssertion,
    GraphBundle,
    Modality,
    OccurrenceRecord,
    PackageSnapshot,
    ParticipantRef,
    Polarity,
    ProducerRef,
    ProjectionRecord,
    Quantifier,
    RelationAssertion,
    SourceFileRecord,
    SubjectRef,
)
from ..fingerprints import (
    ast_sha256,
    minhash_signature,
    normalized_python_tokens,
    simhash64,
    token_shingles,
)
from ..registry import ExtensionRegistry, core_registry

ANALYZER_ID = "taedri.python-syntax"
ANALYZER_VERSION = "0.1.0"
LANGUAGE_KEY = "uceg.language.python"


class UnsafeSourceTreeError(ValueError):
    """A local tree contains a path type the non-executing profile refuses."""


@dataclass(slots=True)
class Scope:
    node: ast.AST
    kind: str
    qualified_name: str
    entity_id: str
    parent: "Scope | None"
    owner_class: "Scope | None" = None
    bindings: dict[str, list[str]] = field(default_factory=dict)
    global_names: set[str] = field(default_factory=set)
    nonlocal_names: set[str] = field(default_factory=set)

    def bind(self, name: str, entity_id: str) -> None:
        values = self.bindings.setdefault(name, [])
        if not values or values[-1] != entity_id:
            values.append(entity_id)

    def binding_scope(self, name: str) -> "Scope":
        if name in self.global_names:
            scope = self
            while scope.parent is not None:
                scope = scope.parent
            return scope
        if name in self.nonlocal_names:
            scope = self.parent
            while scope is not None:
                if name in scope.bindings and scope.kind != "class":
                    return scope
                scope = scope.parent
        return self

    def resolve(self, name: str) -> str | None:
        if name in self.global_names:
            scope = self
            while scope.parent is not None:
                scope = scope.parent
            values = scope.bindings.get(name)
            return values[-1] if values else None
        scope: Scope | None = self
        skip_class_after_function = self.kind in {"function", "lambda", "comprehension"}
        while scope is not None:
            values = scope.bindings.get(name)
            if values:
                return values[-1]
            scope = scope.parent
            if skip_class_after_function and scope is not None and scope.kind == "class":
                scope = scope.parent
            skip_class_after_function = False
        return None


@dataclass(slots=True)
class FileContext:
    bundle: GraphBundle
    file_record: SourceFileRecord
    source: bytes
    text: str
    module_name: str
    producer: ProducerRef
    registry: ExtensionRegistry
    syntax_paths: dict[ast.AST, tuple[str, ...]]
    line_starts: tuple[int, ...]
    scopes: dict[ast.AST, Scope] = field(default_factory=dict)
    entities_by_node: dict[ast.AST, str] = field(default_factory=dict)
    binding_by_node: dict[ast.AST, str] = field(default_factory=dict)
    defining_occurrence_by_node: dict[ast.AST, str] = field(default_factory=dict)
    evidence_by_range: dict[tuple[int, int], str] = field(default_factory=dict)
    external_entities: dict[str, str] = field(default_factory=dict)
    import_targets: dict[str, str] = field(default_factory=dict)

    @property
    def snapshot_id(self) -> str:
        return self.bundle.snapshot.identity.id

    @property
    def analysis_id(self) -> str:
        return self.bundle.analysis.identity.id

    def node_range(self, node: ast.AST) -> tuple[int, int]:
        if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
            return (0, len(self.source))
        start_line = max(int(getattr(node, "lineno", 1)), 1)
        end_line = max(int(getattr(node, "end_lineno", start_line)), start_line)
        start_column = max(int(getattr(node, "col_offset", 0)), 0)
        end_column = max(int(getattr(node, "end_col_offset", start_column)), 0)
        start = self.line_starts[start_line - 1] + start_column
        end = self.line_starts[end_line - 1] + end_column
        return (min(start, len(self.source)), min(max(start, end), len(self.source)))

    def line_columns(self, node: ast.AST) -> tuple[int, int, int, int]:
        return (
            int(getattr(node, "lineno", 1)),
            int(getattr(node, "col_offset", 0)),
            int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
            int(getattr(node, "end_col_offset", getattr(node, "col_offset", 0))),
        )

    def evidence_for(self, node: ast.AST) -> str:
        byte_range = self.node_range(node)
        cached = self.evidence_by_range.get(byte_range)
        if cached:
            return cached
        content = self.source[byte_range[0] : byte_range[1]]
        uri = f"source:{self.file_record.relative_path}#byte={byte_range[0]}-{byte_range[1]}"
        record = EvidenceRecord.create(
            snapshot_id=self.snapshot_id,
            evidence_type_key="uceg.evidence.python.source_range",
            uri=uri,
            content_digest=sha256_digest(content),
            producer=self.producer,
            source_file_id=self.file_record.identity.id,
            file_content_id=self.file_record.content_identity.id,
            byte_range=byte_range,
        )
        self.bundle.evidence[record.identity.id] = record
        self.evidence_by_range[byte_range] = record.identity.id
        return record.identity.id

    def add_occurrence(
        self,
        node: ast.AST,
        *,
        entity_id: str | None,
        enclosing_entity_id: str | None,
        roles: Iterable[str],
    ) -> OccurrenceRecord:
        record = OccurrenceRecord.create(
            snapshot_id=self.snapshot_id,
            source_file_id=self.file_record.identity.id,
            file_content_id=self.file_record.content_identity.id,
            entity_id=entity_id,
            enclosing_entity_id=enclosing_entity_id,
            byte_range=self.node_range(node),
            line_column_range=self.line_columns(node),
            roles=roles,
            syntax_path=self.syntax_paths.get(node, (type(node).__name__,)),
            producer=self.producer,
        )
        self.bundle.occurrences[record.identity.id] = record
        return record

    def add_entity(
        self,
        node: ast.AST,
        *,
        kind: str,
        native_name: str,
        qualified_name: str,
        enclosing_entity_id: str | None,
        roles: Iterable[str] = ("definition",),
        lifecycle: EvidenceLevel = EvidenceLevel.SOURCE_BACKED,
    ) -> EntityRecord:
        byte_range = self.node_range(node)
        record = EntityRecord.create(
            snapshot_id=self.snapshot_id,
            entity_kind_key=kind,
            language_key=LANGUAGE_KEY,
            native_name=native_name,
            qualified_name=qualified_name,
            module_name=self.module_name,
            locator={
                "source_file_id": self.file_record.identity.id,
                "file_content_id": self.file_record.content_identity.id,
                "byte_range": byte_range,
                "syntax_path": self.syntax_paths.get(node, (type(node).__name__,)),
            },
            enclosing_entity_id=enclosing_entity_id,
            lifecycle=lifecycle,
        )
        occurrence = self.add_occurrence(
            node,
            entity_id=record.identity.id,
            enclosing_entity_id=enclosing_entity_id,
            roles=roles,
        )
        record = replace(record, defining_occurrence_id=occurrence.identity.id)
        self.bundle.entities[record.identity.id] = record
        self.entities_by_node[node] = record.identity.id
        self.defining_occurrence_by_node[node] = occurrence.identity.id
        self.evidence_for(node)
        return record

    def add_relation(
        self,
        predicate: str,
        participants: Iterable[tuple[str, str, str, int | None]],
        node: ast.AST,
        *,
        modality: Modality = Modality.EXTRACTED,
        polarity: Polarity = Polarity.POSITIVE,
        quantifier: Quantifier = Quantifier.MUST,
        confidence: float | None = None,
    ) -> RelationAssertion:
        relation = RelationAssertion.create(
            snapshot_id=self.snapshot_id,
            predicate_key=predicate,
            participants=(
                ParticipantRef(role, SubjectRef(subject_kind, subject_id), ordinal)
                for role, subject_kind, subject_id, ordinal in participants
            ),
            modality=modality,
            polarity=polarity,
            quantifier=quantifier,
            producer=self.producer,
            analysis_manifest_id=self.analysis_id,
            evidence_ids=(self.evidence_for(node),),
            confidence=confidence,
        )
        self.bundle.relations[relation.edge_assertion_id] = relation
        synopsis = ProjectionRecord.create(
            subject=SubjectRef("relation", relation.edge_assertion_id),
            projection_key="uceg.description.deterministic.edge_synopsis",
            projection_schema_version="1.0.0",
            input_refs=relation.evidence_ids,
            generator=self.producer,
            payload={
                "text": predicate
                + " "
                + " ".join(
                    f"{participant.role_key}={participant.subject.id}"
                    for participant in relation.participants
                )
            },
            snapshot_id=self.snapshot_id,
        )
        self.bundle.projections[synopsis.identity.id] = synopsis
        return relation

    def add_feature(
        self,
        entity_id: str,
        key: str,
        value: Any,
        node: ast.AST,
    ) -> FeatureAssertion:
        feature = FeatureAssertion.create(
            subject=SubjectRef("entity", entity_id),
            extension_key=key,
            descriptor_version="1.0.0",
            typed_value=value,
            modality=Modality.EXTRACTED,
            polarity=Polarity.POSITIVE,
            producer=self.producer,
            evidence_ids=(self.evidence_for(node),),
            snapshot_id=self.snapshot_id,
        )
        self.registry.validate_feature(feature)
        self.bundle.features[feature.identity.id] = feature
        return feature

    def add_projection(
        self,
        entity_id: str,
        key: str,
        payload: Any,
        node: ast.AST,
    ) -> ProjectionRecord:
        projection = ProjectionRecord.create(
            subject=SubjectRef("entity", entity_id),
            projection_key=key,
            projection_schema_version="1.0.0",
            input_refs=(self.evidence_for(node),),
            generator=self.producer,
            payload=payload,
            snapshot_id=self.snapshot_id,
        )
        self.bundle.projections[projection.identity.id] = projection
        return projection

    def enrich_entity(self, entity_id: str, node: ast.AST, binding_role: str | None = None) -> None:
        entity = self.bundle.entities[entity_id]
        human_kind = entity.entity_kind_key.removeprefix("uceg.entity.").replace(".", " ")
        self.add_projection(
            entity_id,
            "uceg.description.deterministic.synopsis",
            {
                "text": f"{human_kind} `{entity.qualified_name}` declared in "
                f"module `{entity.module_name}`."
            },
            node,
        )
        if binding_role:
            self.add_feature(
                entity_id,
                "uceg.aspect.python.binding_role",
                binding_role,
                node,
            )
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                self.add_projection(
                    entity_id,
                    "uceg.description.source.docstring",
                    {"text": docstring},
                    node,
                )
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = [safe_unparse(item) for item in node.decorator_list]
            self.add_feature(
                entity_id,
                "uceg.aspect.python.decorators",
                decorators,
                node,
            )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            self.add_feature(
                entity_id,
                "uceg.aspect.python.signature",
                function_signature(node),
                node,
            )
        self.add_projection(
            entity_id,
            "uceg.fingerprint.python.ast_sha256",
            {"digest": ast_sha256(node)},
            node,
        )
        segment = ast.get_source_segment(self.text, node) or ""
        tokens = normalized_python_tokens(segment)
        self.add_projection(
            entity_id,
            "uceg.fingerprint.python.token_simhash64",
            {"value": f"{simhash64(tokens):016x}"},
            node,
        )
        self.add_projection(
            entity_id,
            "uceg.fingerprint.python.token_minhash16",
            {
                "values": [
                    f"{value:016x}"
                    for value in minhash_signature(token_shingles(tokens), permutations=16)
                ]
            },
            node,
        )

    def external_entity(self, qualified_name: str, node: ast.AST) -> str:
        qualified_name = qualified_name or "<dynamic>"
        existing = self.external_entities.get(qualified_name)
        if existing:
            return existing
        record = EntityRecord.create(
            snapshot_id=self.snapshot_id,
            entity_kind_key="uceg.entity.external_symbol",
            language_key=LANGUAGE_KEY,
            native_name=qualified_name.rsplit(".", 1)[-1],
            qualified_name=qualified_name,
            module_name=self.module_name,
            locator={
                "external_name": qualified_name,
                "observed_from_source_file": self.file_record.identity.id,
                "observed_from_file_content": self.file_record.content_identity.id,
            },
            lifecycle=EvidenceLevel.CANDIDATE,
        )
        self.bundle.entities[record.identity.id] = record
        self.external_entities[qualified_name] = record.identity.id
        return record.identity.id


class DefinitionCollector(ast.NodeVisitor):
    def __init__(self, context: FileContext, module_scope: Scope):
        self.context = context
        self.scope = module_scope

    def _qualify(self, name: str) -> str:
        return f"{self.scope.qualified_name}.{name}" if self.scope.qualified_name else name

    def _contain(self, entity_id: str, node: ast.AST, enclosing: Scope | None = None) -> None:
        parent = enclosing or self.scope
        self.context.add_relation(
            "uceg.predicate.contains",
            (
                ("uceg.role.container", "entity", parent.entity_id, None),
                ("uceg.role.contained", "entity", entity_id, None),
            ),
            node,
        )
        self.context.add_relation(
            "uceg.predicate.defines",
            (
                ("uceg.role.definer", "entity", parent.entity_id, None),
                ("uceg.role.defined", "entity", entity_id, None),
            ),
            node,
        )

    def _new_binding(
        self,
        node: ast.AST,
        name: str,
        kind: str,
        role: str,
        *,
        scope: Scope | None = None,
        annotation: ast.AST | None = None,
    ) -> str:
        target_scope = (scope or self.scope).binding_scope(name)
        qualified = (
            f"{target_scope.qualified_name}.{name}"
            if target_scope.qualified_name
            else name
        )
        existing = target_scope.bindings.get(name, [])
        if existing and kind in {
            "uceg.entity.python.variable",
            "uceg.entity.python.instance_field",
        }:
            entity_id = existing[-1]
            self.context.binding_by_node[node] = entity_id
            return entity_id
        record = self.context.add_entity(
            node,
            kind=kind,
            native_name=name,
            qualified_name=qualified,
            enclosing_entity_id=target_scope.entity_id,
            roles=("definition", "write"),
        )
        target_scope.bind(name, record.identity.id)
        self.context.binding_by_node[node] = record.identity.id
        self._contain(record.identity.id, node, target_scope)
        self.context.enrich_entity(record.identity.id, node, role)
        if annotation is not None:
            self.context.add_feature(
                record.identity.id,
                "uceg.aspect.python.annotation",
                safe_unparse(annotation),
                annotation,
            )
        return record.identity.id

    def _collect_target(
        self,
        target: ast.AST,
        role: str | None = None,
        annotation: ast.AST | None = None,
    ) -> None:
        if isinstance(target, ast.Name):
            scope_role = role or {
                "module": "module_variable",
                "class": "class_variable",
                "comprehension": "comprehension_target",
            }.get(self.scope.kind, "local_variable")
            self._new_binding(
                target,
                target.id,
                "uceg.entity.python.variable",
                scope_role,
                annotation=annotation,
            )
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._collect_target(item, role, annotation)
        elif isinstance(target, ast.Starred):
            self._collect_target(target.value, role, annotation)
        elif isinstance(target, ast.Attribute):
            if isinstance(target.value, ast.Name) and target.value.id in {"self", "cls"}:
                class_scope = self.scope.owner_class
                if class_scope is not None:
                    self._new_binding(
                        target,
                        target.attr,
                        "uceg.entity.python.instance_field",
                        "instance_field",
                        scope=class_scope,
                        annotation=annotation,
                    )

    def _collect_arguments(self, node: ast.arguments, scope: Scope) -> None:
        positional = [*node.posonlyargs, *node.args]
        for argument in positional:
            self._parameter(argument, scope, "positional")
        if node.vararg:
            self._parameter(node.vararg, scope, "variadic_positional")
        for argument in node.kwonlyargs:
            self._parameter(argument, scope, "keyword_only")
        if node.kwarg:
            self._parameter(node.kwarg, scope, "variadic_keyword")

    def _parameter(self, node: ast.arg, scope: Scope, parameter_kind: str) -> None:
        qualified = f"{scope.qualified_name}.{node.arg}"
        record = self.context.add_entity(
            node,
            kind="uceg.entity.python.parameter",
            native_name=node.arg,
            qualified_name=qualified,
            enclosing_entity_id=scope.entity_id,
            roles=("definition", "parameter"),
        )
        scope.bind(node.arg, record.identity.id)
        self.context.binding_by_node[node] = record.identity.id
        self._contain(record.identity.id, node, scope)
        self.context.enrich_entity(record.identity.id, node, f"parameter:{parameter_kind}")
        if node.annotation:
            self.context.add_feature(
                record.identity.id,
                "uceg.aspect.python.annotation",
                safe_unparse(node.annotation),
                node.annotation,
            )

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # Decorators, defaults, and annotations are evaluated in the enclosing
        # scope. Their lambdas/comprehensions must therefore be inventoried before
        # entering the function's lexical scope.
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [
            *node.args.defaults,
            *[item for item in node.args.kw_defaults if item is not None],
        ]:
            self.visit(default)
        for argument in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            *([node.args.vararg] if node.args.vararg else []),
            *([node.args.kwarg] if node.args.kwarg else []),
        ]:
            if argument.annotation:
                self.visit(argument.annotation)
        if node.returns:
            self.visit(node.returns)
        if self.scope.kind == "class":
            suffix = "async_method" if isinstance(node, ast.AsyncFunctionDef) else "method"
        elif self.scope.kind in {"function", "lambda"}:
            suffix = "nested_function"
        else:
            suffix = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
        qualified = self._qualify(node.name)
        record = self.context.add_entity(
            node,
            kind=f"uceg.entity.python.{suffix}",
            native_name=node.name,
            qualified_name=qualified,
            enclosing_entity_id=self.scope.entity_id,
        )
        self.scope.bind(node.name, record.identity.id)
        self._contain(record.identity.id, node)
        self.context.enrich_entity(record.identity.id, node)
        child = Scope(
            node,
            "function",
            qualified,
            record.identity.id,
            self.scope,
            self.scope if self.scope.kind == "class" else self.scope.owner_class,
        )
        for statement in node.body:
            if isinstance(statement, ast.Global):
                child.global_names.update(statement.names)
            elif isinstance(statement, ast.Nonlocal):
                child.nonlocal_names.update(statement.names)
        self.context.scopes[node] = child
        previous = self.scope
        self.scope = child
        self._collect_arguments(node.args, child)
        for statement in node.body:
            self.visit(statement)
        self.scope = previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword_node in node.keywords:
            self.visit(keyword_node.value)
        qualified = self._qualify(node.name)
        record = self.context.add_entity(
            node,
            kind="uceg.entity.python.class",
            native_name=node.name,
            qualified_name=qualified,
            enclosing_entity_id=self.scope.entity_id,
        )
        self.scope.bind(node.name, record.identity.id)
        self._contain(record.identity.id, node)
        self.context.enrich_entity(record.identity.id, node)
        child = Scope(node, "class", qualified, record.identity.id, self.scope)
        child.owner_class = child
        self.context.scopes[node] = child
        previous = self.scope
        self.scope = child
        for statement in node.body:
            self.visit(statement)
        self.scope = previous

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in [
            *node.args.defaults,
            *[item for item in node.args.kw_defaults if item is not None],
        ]:
            self.visit(default)
        name = f"<lambda@{getattr(node, 'lineno', 0)}:{getattr(node, 'col_offset', 0)}>"
        qualified = self._qualify(name)
        record = self.context.add_entity(
            node,
            kind="uceg.entity.python.lambda",
            native_name=name,
            qualified_name=qualified,
            enclosing_entity_id=self.scope.entity_id,
        )
        self._contain(record.identity.id, node)
        self.context.enrich_entity(record.identity.id, node)
        child = Scope(
            node,
            "lambda",
            qualified,
            record.identity.id,
            self.scope,
            self.scope.owner_class,
        )
        self.context.scopes[node] = child
        previous = self.scope
        self.scope = child
        self._collect_arguments(node.args, child)
        self.visit(node.body)
        self.scope = previous

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._collect_target(target)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._collect_target(node.target, annotation=node.annotation)
        if node.value:
            self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._collect_target(node.target)
        self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._collect_target(node.target, "assignment_expression_target")
        self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:
        self._collect_target(node.target, "loop_target")
        self.generic_visit(node)

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars:
                self._collect_target(item.optional_vars, "context_manager_target")
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._new_binding(
                node,
                node.name,
                "uceg.entity.python.variable",
                "exception_target",
            )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            binding = alias.asname or alias.name.split(".", 1)[0]
            entity_id = self._new_binding(
                alias,
                binding,
                "uceg.entity.python.import_binding",
                "import_binding",
            )
            self.context.import_targets[entity_id] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            binding = alias.asname or alias.name
            entity_id = self._new_binding(
                alias,
                binding,
                "uceg.entity.python.import_binding",
                "import_binding",
            )
            self.context.import_targets[entity_id] = f"{module}.{alias.name}".strip(".")

    def _comprehension(self, node: ast.AST, generators: list[ast.comprehension]) -> None:
        name = f"<comprehension@{getattr(node, 'lineno', 0)}:{getattr(node, 'col_offset', 0)}>"
        qualified = self._qualify(name)
        record = self.context.add_entity(
            node,
            kind="uceg.entity.python.comprehension_scope",
            native_name=name,
            qualified_name=qualified,
            enclosing_entity_id=self.scope.entity_id,
        )
        self._contain(record.identity.id, node)
        child = Scope(
            node,
            "comprehension",
            qualified,
            record.identity.id,
            self.scope,
            self.scope.owner_class,
        )
        self.context.scopes[node] = child
        previous = self.scope
        self.scope = child
        for generator in generators:
            self._collect_target(generator.target, "comprehension_target")
            self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        for field_name in ("elt", "key", "value"):
            child_node = getattr(node, field_name, None)
            if child_node is not None:
                self.visit(child_node)
        self.scope = previous

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._comprehension(node, node.generators)

    visit_SetComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._comprehension(node, node.generators)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self._new_binding(
                node,
                node.name,
                "uceg.entity.python.variable",
                "pattern_capture",
            )
        if node.pattern:
            self.visit(node.pattern)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._new_binding(
                node,
                node.name,
                "uceg.entity.python.variable",
                "pattern_capture",
            )

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self._new_binding(
                node,
                node.rest,
                "uceg.entity.python.variable",
                "pattern_capture",
            )
        for pattern in node.patterns:
            self.visit(pattern)


class OccurrenceCollector(ast.NodeVisitor):
    def __init__(self, context: FileContext, module_scope: Scope):
        self.context = context
        self.scope = module_scope

    def _current_entity(self) -> str:
        return self.scope.entity_id

    def _occurrence(self, node: ast.AST, entity_id: str, role: str) -> str:
        definition = self.context.defining_occurrence_by_node.get(node)
        if definition and role == "write":
            return definition
        occurrence = self.context.add_occurrence(
            node,
            entity_id=entity_id,
            enclosing_entity_id=self._current_entity(),
            roles=(role, "reference") if role != "call" else ("call",),
        )
        return occurrence.identity.id

    def _access(self, node: ast.AST, entity_id: str, role: str) -> None:
        occurrence_id = self._occurrence(node, entity_id, role)
        predicate = {
            "read": "uceg.predicate.reads",
            "write": "uceg.predicate.writes",
            "delete": "uceg.predicate.deletes",
        }[role]
        agent_role = {
            "read": "uceg.role.reader",
            "write": "uceg.role.writer",
            "delete": "uceg.role.deleter",
        }[role]
        site_role = {
            "read": "uceg.role.readsite",
            "write": "uceg.role.writesite",
            "delete": "uceg.role.deletesite",
        }[role]
        self.context.add_relation(
            predicate,
            (
                (agent_role, "entity", self._current_entity(), None),
                ("uceg.role.value", "entity", entity_id, None),
                (site_role, "occurrence", occurrence_id, None),
            ),
            node,
        )
        self.context.add_relation(
            "uceg.predicate.references",
            (
                ("uceg.role.referencer", "entity", self._current_entity(), None),
                ("uceg.role.referenced", "entity", entity_id, None),
                ("uceg.role.reference_site", "occurrence", occurrence_id, None),
            ),
            node,
        )

    def _enter(self, node: ast.AST) -> Scope:
        previous = self.scope
        self.scope = self.context.scopes[node]
        return previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *[item for item in node.args.kw_defaults if item]]:
            self.visit(default)
        if node.returns:
            self.visit(node.returns)
        previous = self._enter(node)
        for statement in node.body:
            self.visit(statement)
        self.scope = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_id = self.context.entities_by_node[node]
        for base in node.bases:
            target = self._resolve_expression(base)
            self.context.add_relation(
                "uceg.predicate.extends",
                (
                    ("uceg.role.subtype", "entity", class_id, None),
                    ("uceg.role.supertype", "entity", target, None),
                ),
                base,
                modality=Modality.INFERRED,
                quantifier=Quantifier.MAY,
            )
            self.visit(base)
        for decorator in node.decorator_list:
            self.visit(decorator)
        previous = self._enter(node)
        for statement in node.body:
            self.visit(statement)
        self.scope = previous

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in [*node.args.defaults, *[item for item in node.args.kw_defaults if item]]:
            self.visit(default)
        previous = self._enter(node)
        self.visit(node.body)
        self.scope = previous

    def visit_Name(self, node: ast.Name) -> None:
        entity_id = self.context.binding_by_node.get(node) or self.scope.resolve(node.id)
        if entity_id is None:
            entity_id = self.context.external_entity(node.id, node)
        role = "read" if isinstance(node.ctx, ast.Load) else "delete" if isinstance(node.ctx, ast.Del) else "write"
        self._access(node, entity_id, role)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        entity_id = self.context.binding_by_node.get(node)
        if entity_id is None and isinstance(node.value, ast.Name) and node.value.id in {"self", "cls"}:
            owner = self.scope.owner_class
            if owner:
                values = owner.bindings.get(node.attr)
                entity_id = values[-1] if values else None
        if entity_id is not None:
            role = "read" if isinstance(node.ctx, ast.Load) else "delete" if isinstance(node.ctx, ast.Del) else "write"
            self._access(node, entity_id, role)
        self.visit(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        callee = self._resolve_expression(node.func)
        occurrence = self.context.add_occurrence(
            node,
            entity_id=None,
            enclosing_entity_id=self._current_entity(),
            roles=("call",),
        )
        self.context.add_relation(
            "uceg.predicate.calls_may",
            (
                ("uceg.role.caller", "entity", self._current_entity(), None),
                ("uceg.role.callee", "entity", callee, None),
                ("uceg.role.callsite", "occurrence", occurrence.identity.id, None),
            ),
            node,
            modality=Modality.INFERRED,
            quantifier=Quantifier.MAY,
        )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self._import(node, node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._import(node, node.names)

    def _import(self, node: ast.AST, aliases: list[ast.alias]) -> None:
        for alias in aliases:
            entity_id = self.context.binding_by_node.get(alias)
            if entity_id is None:
                continue
            target_name = self.context.import_targets[entity_id]
            target_id = self.context.external_entity(target_name, alias)
            occurrence_id = self.context.defining_occurrence_by_node[alias]
            self.context.add_relation(
                "uceg.predicate.imports",
                (
                    ("uceg.role.importer", "entity", self._current_entity(), None),
                    ("uceg.role.imported", "entity", target_id, None),
                    ("uceg.role.import_site", "occurrence", occurrence_id, None),
                    ("uceg.role.binding", "entity", entity_id, None),
                ),
                alias,
            )

    def _comprehension(self, node: ast.AST, generators: list[ast.comprehension]) -> None:
        if not generators:
            return
        # Python evaluates the outermost iterable in the enclosing scope before
        # entering the comprehension's implicit function scope.
        self.visit(generators[0].iter)
        previous = self._enter(node)
        first, *remaining = generators
        self.visit(first.target)
        for condition in first.ifs:
            self.visit(condition)
        for generator in remaining:
            self.visit(generator.iter)
            self.visit(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for field_name in ("elt", "key", "value"):
            value = getattr(node, field_name, None)
            if value is not None:
                self.visit(value)
        self.scope = previous

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type:
            self.visit(node.type)
        entity_id = self.context.binding_by_node.get(node)
        if entity_id is not None:
            self._access(node, entity_id, "write")
        for statement in node.body:
            self.visit(statement)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        entity_id = self.context.binding_by_node.get(node)
        if entity_id is not None:
            self._access(node, entity_id, "write")
        if node.pattern:
            self.visit(node.pattern)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        entity_id = self.context.binding_by_node.get(node)
        if entity_id is not None:
            self._access(node, entity_id, "write")

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        entity_id = self.context.binding_by_node.get(node)
        if entity_id is not None:
            self._access(node, entity_id, "write")
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._comprehension(node, node.generators)

    visit_SetComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._comprehension(node, node.generators)

    def _resolve_expression(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            resolved = self.scope.resolve(node.id)
            if resolved:
                imported = self.context.import_targets.get(resolved)
                return self.context.external_entity(imported, node) if imported else resolved
        if isinstance(node, ast.Attribute):
            chain = dotted_name(node)
            if chain:
                root = chain.split(".", 1)[0]
                root_id = self.scope.resolve(root)
                imported = self.context.import_targets.get(root_id or "")
                if imported:
                    suffix = chain.split(".", 1)[1] if "." in chain else ""
                    return self.context.external_entity(
                        f"{imported}.{suffix}".rstrip("."), node
                    )
                if root in {"self", "cls"} and self.scope.owner_class:
                    values = self.scope.owner_class.bindings.get(node.attr)
                    if values:
                        return values[-1]
                return self.context.external_entity(chain, node)
        return self.context.external_entity(dotted_name(node) or "<dynamic-call-target>", node)


class PythonSyntaxAnalyzer:
    def __init__(self, registry: ExtensionRegistry | None = None) -> None:
        self.registry = registry or core_registry()
        config = {
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": ANALYZER_VERSION,
            "parser": f"cpython-ast-{sys.version_info.major}.{sys.version_info.minor}",
            "follow_symlinks": False,
            "execute": False,
            "network": False,
        }
        self.config_digest = canonical_digest(config)
        self.producer = ProducerRef(ANALYZER_ID, ANALYZER_VERSION, self.config_digest)

    def analyze(
        self,
        root: str | os.PathLike[str],
        *,
        package_name: str | None = None,
        release: str | None = None,
    ) -> GraphBundle:
        root_path = Path(root).resolve(strict=True)
        if not root_path.is_dir():
            raise ValueError(f"analysis root is not a directory: {root_path}")
        discovered = discover_python_files(root_path)
        file_records: dict[str, SourceFileRecord] = {}
        contents: dict[str, bytes] = {}
        for relative_path, content in discovered:
            record = SourceFileRecord.create(relative_path, content)
            file_records[record.identity.id] = record
            contents[record.content_digest] = content
        root_digest = canonical_digest(
            [
                {
                    "relative_path": record.relative_path,
                    "source_file_id": record.identity.id,
                    "file_content_id": record.content_identity.id,
                    "content_digest": record.content_digest,
                }
                for record in sorted(file_records.values(), key=lambda item: item.relative_path)
            ]
        )
        snapshot = PackageSnapshot.create(
            source_kind="local_python_tree",
            # The mutable checkout location is deliberately not part of the graph
            # fact shard. Exact origin receipts will be added by source adapters.
            source_uri=f"local-tree:{package_name or root_path.name}",
            package_name=package_name or root_path.name,
            release=release,
            language_key=LANGUAGE_KEY,
            root_digest=root_digest,
            file_ids=file_records,
            interpreter=f"cpython-{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        analysis = AnalysisManifest.create(
            snapshot_id=snapshot.identity.id,
            analyzer_id=ANALYZER_ID,
            analyzer_version=ANALYZER_VERSION,
            config_digest=self.config_digest,
            profile="syntax-only",
        )
        bundle = GraphBundle(
            snapshot=snapshot,
            analysis=analysis,
            files=file_records,
            source_blobs=contents,
        )
        successes = 0
        unsupported: list[str] = []
        for file_record in sorted(file_records.values(), key=lambda item: item.relative_path):
            content = contents[file_record.content_digest]
            try:
                text = content.decode("utf-8-sig")
                tree = ast.parse(
                    text,
                    filename=file_record.relative_path,
                    type_comments=True,
                    feature_version=(3, 12),
                )
            except (UnicodeDecodeError, SyntaxError) as exc:
                unsupported.append(f"{file_record.relative_path}:{type(exc).__name__}")
                continue
            module_name = module_name_for(file_record.relative_path, snapshot.package_name)
            paths = syntax_paths(tree)
            context = FileContext(
                bundle,
                file_record,
                content,
                text,
                module_name,
                self.producer,
                self.registry,
                paths,
                byte_line_starts(content),
            )
            self._analyze_file(context, tree)
            successes += 1

        state = (
            CompletenessState.COMPLETE_FOR_DECLARED_SYNTAX
            if successes == len(file_records)
            else CompletenessState.ATTEMPTED_PARTIAL
        )
        coverage = CoverageLedger.create(
            snapshot_id=snapshot.identity.id,
            family_key="uceg.coverage.python.syntax",
            attempted_inputs=len(file_records),
            successful_inputs=successes,
            unresolved_inputs=len(file_records) - successes,
            unsupported_constructs=unsupported,
            completeness_state=state,
            extractor_versions=(f"{ANALYZER_ID}@{ANALYZER_VERSION}",),
        )
        bundle.coverage[coverage.identity.id] = coverage
        bundle.validate(self.registry.resolve)
        return bundle

    def _analyze_file(self, context: FileContext, tree: ast.Module) -> None:
        file_entity = context.add_entity(
            tree,
            kind="uceg.entity.file",
            native_name=context.file_record.relative_path.rsplit("/", 1)[-1],
            qualified_name=context.file_record.relative_path,
            enclosing_entity_id=None,
        )
        module_entity = context.add_entity(
            tree,
            kind="uceg.entity.python.module",
            native_name=context.module_name.rsplit(".", 1)[-1],
            qualified_name=context.module_name,
            enclosing_entity_id=file_entity.identity.id,
        )
        context.add_relation(
            "uceg.predicate.contains",
            (
                ("uceg.role.container", "entity", file_entity.identity.id, None),
                ("uceg.role.contained", "entity", module_entity.identity.id, None),
            ),
            tree,
        )
        context.enrich_entity(module_entity.identity.id, tree)
        module_scope = Scope(
            tree,
            "module",
            context.module_name,
            module_entity.identity.id,
            None,
        )
        context.scopes[tree] = module_scope
        DefinitionCollector(context, module_scope).visit(tree)
        OccurrenceCollector(context, module_scope).visit(tree)


def discover_python_files(root: Path) -> tuple[tuple[str, bytes], ...]:
    discovered: list[tuple[str, bytes]] = []
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        kept_directories: list[str] = []
        for name in sorted(dirnames):
            candidate = directory_path / name
            if candidate.is_symlink():
                continue
            kept_directories.append(name)
        dirnames[:] = kept_directories
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            candidate = directory_path / filename
            if candidate.is_symlink():
                raise UnsafeSourceTreeError(f"refusing symlinked Python file: {candidate}")
            if not candidate.is_file():
                raise UnsafeSourceTreeError(f"refusing non-regular Python path: {candidate}")
            relative = candidate.relative_to(root).as_posix()
            discovered.append((relative, candidate.read_bytes()))
    return tuple(sorted(discovered, key=lambda item: item[0]))


def module_name_for(relative_path: str, package_name: str) -> str:
    parts = relative_path.split("/")
    filename = parts.pop()
    stem = filename[:-3]
    if stem != "__init__":
        parts.append(stem)
    normalized_package = package_name.replace("-", "_")
    if parts and parts[0] == normalized_package:
        return ".".join(parts) or normalized_package
    return ".".join((normalized_package, *parts)) if parts else normalized_package


def byte_line_starts(content: bytes) -> tuple[int, ...]:
    starts = [0]
    for index, value in enumerate(content):
        if value == 0x0A:
            starts.append(index + 1)
    starts.append(len(content))
    return tuple(starts)


def syntax_paths(root: ast.AST) -> dict[ast.AST, tuple[str, ...]]:
    paths: dict[ast.AST, tuple[str, ...]] = {root: (type(root).__name__,)}

    def walk(node: ast.AST) -> None:
        parent = paths[node]
        for field_name, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                paths[value] = (*parent, f"{field_name}:{type(value).__name__}")
                walk(value)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    if isinstance(child, ast.AST):
                        paths[child] = (
                            *parent,
                            f"{field_name}[{index}]:{type(child).__name__}",
                        )
                        walk(child)

    walk(root)
    return paths


def safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except (ValueError, TypeError, RecursionError):
        return ast.dump(node, include_attributes=False)


def function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> dict[str, Any]:
    arguments = node.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults: list[ast.AST | None] = [None] * (len(positional) - len(arguments.defaults)) + list(
        arguments.defaults
    )
    parameters: list[dict[str, Any]] = []
    for index, (argument, default) in enumerate(zip(positional, defaults, strict=True)):
        parameters.append(
            {
                "name": argument.arg,
                "kind": "positional_only" if index < len(arguments.posonlyargs) else "positional_or_keyword",
                "annotation": safe_unparse(argument.annotation) or None,
                "default": safe_unparse(default) or None,
            }
        )
    if arguments.vararg:
        parameters.append(
            {
                "name": arguments.vararg.arg,
                "kind": "variadic_positional",
                "annotation": safe_unparse(arguments.vararg.annotation) or None,
                "default": None,
            }
        )
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
        parameters.append(
            {
                "name": argument.arg,
                "kind": "keyword_only",
                "annotation": safe_unparse(argument.annotation) or None,
                "default": safe_unparse(default) or None,
            }
        )
    if arguments.kwarg:
        parameters.append(
            {
                "name": arguments.kwarg.arg,
                "kind": "variadic_keyword",
                "annotation": safe_unparse(arguments.kwarg.annotation) or None,
                "default": None,
            }
        )
    return {
        "parameters": parameters,
        "returns": safe_unparse(getattr(node, "returns", None)) or None,
        "async": isinstance(node, ast.AsyncFunctionDef),
    }


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None
