"""Additive source-adapter registry and a safe polyglot inventory POC."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Protocol

from .canonical import canonical_digest
from .contracts import (
    AnalysisManifest,
    CompletenessState,
    CoverageLedger,
    EntityRecord,
    EvidenceRecord,
    GraphBundle,
    Modality,
    PackageSnapshot,
    ParticipantRef,
    Polarity,
    ProducerRef,
    Quantifier,
    RelationAssertion,
    SourceFileRecord,
    SubjectRef,
)
from .representations import core_representation_registry, enrich_bundle_representations

MAX_SOURCE_FILE_BYTES = 16 * 1024 * 1024
IGNORED_DIRECTORIES = frozenset(
    {".git", ".hg", ".svn", ".tcg", ".venv", "venv", "node_modules", "target", "dist", "build"}
)

LANGUAGES: dict[str, tuple[str, str]] = {
    ".py": ("uceg.language.python", "text/x-python"),
    ".pyi": ("uceg.language.python", "text/x-python-stub"),
    ".js": ("uceg.language.javascript", "text/javascript"),
    ".jsx": ("uceg.language.javascript", "text/jsx"),
    ".ts": ("uceg.language.typescript", "text/typescript"),
    ".tsx": ("uceg.language.typescript", "text/tsx"),
    ".java": ("uceg.language.java", "text/x-java-source"),
    ".kt": ("uceg.language.kotlin", "text/x-kotlin"),
    ".go": ("uceg.language.go", "text/x-go"),
    ".rs": ("uceg.language.rust", "text/x-rust"),
    ".c": ("uceg.language.c", "text/x-c"),
    ".h": ("uceg.language.c", "text/x-c-header"),
    ".cc": ("uceg.language.cpp", "text/x-c++"),
    ".cpp": ("uceg.language.cpp", "text/x-c++"),
    ".hpp": ("uceg.language.cpp", "text/x-c++-header"),
    ".cs": ("uceg.language.csharp", "text/x-csharp"),
    ".rb": ("uceg.language.ruby", "text/x-ruby"),
    ".php": ("uceg.language.php", "application/x-httpd-php"),
    ".swift": ("uceg.language.swift", "text/x-swift"),
    ".scala": ("uceg.language.scala", "text/x-scala"),
    ".sh": ("uceg.language.shell", "text/x-shellscript"),
}


class SourceAdapter(Protocol):
    adapter_key: str
    adapter_version: str

    def analyze(self, source: Path, *, package_name: str | None = None) -> GraphBundle: ...


class SourceAdapterRegistry:
    """Runtime-extensible adapter registry with immutable key/version meaning."""

    def __init__(self) -> None:
        self._adapters: dict[tuple[str, str], SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        key = (adapter.adapter_key, adapter.adapter_version)
        existing = self._adapters.get(key)
        if existing is not None and type(existing) is not type(adapter):
            raise ValueError(
                f"cannot reinterpret source adapter {adapter.adapter_key}@{adapter.adapter_version}"
            )
        self._adapters[key] = adapter

    def resolve(self, adapter_key: str, adapter_version: str) -> SourceAdapter:
        try:
            return self._adapters[(adapter_key, adapter_version)]
        except KeyError as exc:
            raise KeyError(f"unknown source adapter {adapter_key}@{adapter_version}") from exc

    def manifest(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "adapter_key": key,
                "adapter_version": version,
                "implementation": f"{type(adapter).__module__}.{type(adapter).__qualname__}",
            }
            for (key, version), adapter in sorted(self._adapters.items())
        )


class InterchangeImporter(Protocol):
    """Boundary for SCIP, CPG, CodeQL, or future semantic index imports."""

    format_key: str
    format_version: str

    def import_into(self, bundle: GraphBundle, artifact: Path) -> None: ...


class InterchangeRegistry:
    def __init__(self) -> None:
        self._importers: dict[tuple[str, str], InterchangeImporter] = {}

    def register(self, importer: InterchangeImporter) -> None:
        key = (importer.format_key, importer.format_version)
        if key in self._importers and type(self._importers[key]) is not type(importer):
            raise ValueError(f"cannot reinterpret interchange importer {key[0]}@{key[1]}")
        self._importers[key] = importer

    def resolve(self, format_key: str, format_version: str) -> InterchangeImporter:
        return self._importers[(format_key, format_version)]


def discover_polyglot_sources(root: Path) -> tuple[tuple[str, bytes, str, str], ...]:
    discovered: list[tuple[str, bytes, str, str]] = []
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        dirnames[:] = [
            name
            for name in sorted(dirnames)
            if name not in IGNORED_DIRECTORIES and not (directory_path / name).is_symlink()
        ]
        for filename in sorted(filenames):
            candidate = directory_path / filename
            language = LANGUAGES.get(candidate.suffix.lower())
            if language is None:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError(f"refusing non-regular source path: {candidate}")
            if candidate.stat().st_size > MAX_SOURCE_FILE_BYTES:
                raise ValueError(f"source file exceeds inventory limit: {candidate}")
            relative = candidate.relative_to(root).as_posix()
            discovered.append((relative, candidate.read_bytes(), *language))
    return tuple(sorted(discovered, key=lambda item: item[0]))


class PolyglotInventoryAnalyzer:
    """Language-neutral file/entity layer; semantic adapters can enrich it later."""

    adapter_key = "taedri.source.polyglot-inventory"
    adapter_version = "0.1.0"

    def __init__(self) -> None:
        self.config_digest = canonical_digest(
            {
                "adapter_key": self.adapter_key,
                "adapter_version": self.adapter_version,
                "languages": sorted(LANGUAGES),
                "max_source_file_bytes": MAX_SOURCE_FILE_BYTES,
                "follow_symlinks": False,
                "execute": False,
            }
        )
        self.producer = ProducerRef(
            self.adapter_key, self.adapter_version, self.config_digest
        )

    def analyze(
        self,
        source: Path | str,
        *,
        package_name: str | None = None,
        release: str | None = None,
        source_uri: str | None = None,
    ) -> GraphBundle:
        root = Path(source).resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"inventory root is not a directory: {root}")
        discovered = discover_polyglot_sources(root)
        files: dict[str, SourceFileRecord] = {}
        blobs: dict[str, bytes] = {}
        language_by_file: dict[str, str] = {}
        for relative, content, language, media_type in discovered:
            record = SourceFileRecord.create(relative, content, media_type)
            files[record.identity.id] = record
            blobs[record.content_digest] = content
            language_by_file[record.identity.id] = language
        languages = sorted(set(language_by_file.values()))
        language_key = languages[0] if len(languages) == 1 else "uceg.language.polyglot"
        inventory_digest = canonical_digest(
            [
                {
                    "relative_path": record.relative_path,
                    "content_digest": record.content_digest,
                    "media_type": record.media_type,
                }
                for record in sorted(files.values(), key=lambda item: item.relative_path)
            ]
        )
        name = package_name or root.name
        snapshot = PackageSnapshot.create(
            source_kind="polyglot_source_tree",
            source_uri=source_uri or f"local-tree:{name}",
            package_name=name,
            release=release,
            language_key=language_key,
            root_digest=inventory_digest,
            file_ids=files,
            interpreter=f"inventory-python-{sys.version_info.major}.{sys.version_info.minor}",
        )
        analysis = AnalysisManifest.create(
            snapshot_id=snapshot.identity.id,
            analyzer_id=self.adapter_key,
            analyzer_version=self.adapter_version,
            config_digest=self.config_digest,
            profile="inventory-only",
        )
        bundle = GraphBundle(snapshot, analysis, files=files, source_blobs=blobs)
        root_entity = EntityRecord.create(
            snapshot_id=snapshot.identity.id,
            entity_kind_key="uceg.entity.source_root",
            language_key=language_key,
            native_name=name,
            qualified_name=name,
            module_name=name,
            locator={"inventory_digest": inventory_digest},
        )
        bundle.entities[root_entity.identity.id] = root_entity
        for file_id, record in sorted(files.items(), key=lambda item: item[1].relative_path):
            file_entity = EntityRecord.create(
                snapshot_id=snapshot.identity.id,
                entity_kind_key="uceg.entity.file",
                language_key=language_by_file[file_id],
                native_name=record.relative_path.rsplit("/", 1)[-1],
                qualified_name=record.relative_path,
                module_name=name,
                locator={
                    "source_file_id": file_id,
                    "file_content_id": record.content_identity.id,
                    "byte_range": (0, record.size_bytes),
                },
                enclosing_entity_id=root_entity.identity.id,
            )
            bundle.entities[file_entity.identity.id] = file_entity
            evidence = EvidenceRecord.create(
                snapshot_id=snapshot.identity.id,
                evidence_type_key="uceg.evidence.source.file",
                uri=f"source:{record.relative_path}",
                content_digest=record.content_digest,
                producer=self.producer,
                source_file_id=file_id,
                file_content_id=record.content_identity.id,
                byte_range=(0, record.size_bytes),
            )
            bundle.evidence[evidence.identity.id] = evidence
            relation = RelationAssertion.create(
                snapshot_id=snapshot.identity.id,
                predicate_key="uceg.predicate.contains",
                participants=(
                    ParticipantRef("uceg.role.container", SubjectRef("entity", root_entity.identity.id)),
                    ParticipantRef("uceg.role.contained", SubjectRef("entity", file_entity.identity.id)),
                ),
                modality=Modality.EXTRACTED,
                polarity=Polarity.POSITIVE,
                quantifier=Quantifier.MUST,
                producer=self.producer,
                analysis_manifest_id=analysis.identity.id,
                evidence_ids=(evidence.identity.id,),
            )
            bundle.relations[relation.edge_assertion_id] = relation
        coverage = CoverageLedger.create(
            snapshot_id=snapshot.identity.id,
            family_key="uceg.coverage.source.inventory",
            attempted_inputs=len(files),
            successful_inputs=len(files),
            unresolved_inputs=0,
            unsupported_constructs=(),
            completeness_state=CompletenessState.COMPLETE_FOR_DECLARED_SYNTAX,
            extractor_versions=(f"{self.adapter_key}@{self.adapter_version}",),
        )
        bundle.coverage[coverage.identity.id] = coverage
        enrich_bundle_representations(bundle)
        bundle.validate(
            representation_descriptor_lookup=core_representation_registry().resolve
        )
        return bundle


def core_source_adapters() -> SourceAdapterRegistry:
    registry = SourceAdapterRegistry()
    registry.register(PolyglotInventoryAnalyzer())
    return registry
