"""Additive extension registry and conformance checks."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from .contracts import ExtensionDescriptor, FeatureAssertion


class RegistryConflictError(ValueError):
    """A descriptor version was reinterpreted instead of versioned additively."""


class ExtensionRegistry:
    def __init__(self) -> None:
        self._descriptors: dict[tuple[str, str], ExtensionDescriptor] = {}
        self._versions: dict[str, set[str]] = defaultdict(set)

    def register(self, descriptor: ExtensionDescriptor) -> None:
        key = (descriptor.extension_key, descriptor.descriptor_version)
        existing = self._descriptors.get(key)
        if existing is not None and existing.descriptor_digest != descriptor.descriptor_digest:
            raise RegistryConflictError(
                f"cannot reinterpret {descriptor.extension_key}@{descriptor.descriptor_version}; "
                "publish a new version or key"
            )
        self._descriptors[key] = descriptor
        self._versions[descriptor.extension_key].add(descriptor.descriptor_version)

    def register_many(self, descriptors: Iterable[ExtensionDescriptor]) -> None:
        for descriptor in descriptors:
            self.register(descriptor)

    def resolve(self, extension_key: str, descriptor_version: str) -> ExtensionDescriptor:
        try:
            return self._descriptors[(extension_key, descriptor_version)]
        except KeyError as exc:
            raise KeyError(f"unknown extension {extension_key}@{descriptor_version}") from exc

    def versions(self, extension_key: str) -> tuple[str, ...]:
        return tuple(sorted(self._versions.get(extension_key, ())))

    def descriptors(self) -> tuple[ExtensionDescriptor, ...]:
        return tuple(
            self._descriptors[key]
            for key in sorted(self._descriptors)
        )

    def validate_feature(self, feature: FeatureAssertion) -> None:
        descriptor = self.resolve(feature.extension_key, feature.descriptor_version)
        if feature.subject.subject_kind not in descriptor.applies_to:
            raise ValueError(
                f"{feature.extension_key} does not apply to {feature.subject.subject_kind}"
            )
        value = feature.typed_value
        valid = {
            "string": lambda item: isinstance(item, str),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "structured": lambda item: isinstance(item, dict | list),
            "string_list": lambda item: isinstance(item, list)
            and all(isinstance(part, str) for part in item),
            "digest": lambda item: isinstance(item, str) and item.startswith("sha256:"),
            "hex": lambda item: isinstance(item, str)
            and bool(item)
            and all(character in "0123456789abcdef" for character in item),
        }.get(descriptor.wire_type)
        if valid is None:
            raise ValueError(f"unsupported registry wire type: {descriptor.wire_type}")
        if not valid(value):
            raise ValueError(
                f"value for {feature.extension_key} does not conform to "
                f"wire type {descriptor.wire_type}"
            )

    def manifest(self) -> list[dict[str, Any]]:
        return [descriptor.to_dict() for descriptor in self.descriptors()]


def core_registry() -> ExtensionRegistry:
    registry = ExtensionRegistry()
    common = {"authority": "https://taedri.dev/registry", "applies_to": ("entity",)}
    registry.register_many(
        [
            ExtensionDescriptor(
                "uceg.aspect.python.signature",
                "1.0.0",
                wire_type="structured",
                missing_value_semantics="unknown",
                exact_index=True,
                **common,
            ),
            ExtensionDescriptor(
                "uceg.aspect.python.decorators",
                "1.0.0",
                wire_type="string_list",
                missing_value_semantics="empty_is_meaningful",
                lexical_index=True,
                **common,
            ),
            ExtensionDescriptor(
                "uceg.aspect.python.binding_role",
                "1.0.0",
                wire_type="string",
                missing_value_semantics="unknown",
                exact_index=True,
                **common,
            ),
            ExtensionDescriptor(
                "uceg.aspect.python.annotation",
                "1.0.0",
                wire_type="string",
                missing_value_semantics="unknown",
                exact_index=True,
                lexical_index=True,
                **common,
            ),
            ExtensionDescriptor(
                "uceg.description.source.docstring",
                "1.0.0",
                wire_type="string",
                missing_value_semantics="unknown",
                lexical_index=True,
                **common,
            ),
            ExtensionDescriptor(
                "uceg.description.deterministic.synopsis",
                "1.0.0",
                wire_type="string",
                missing_value_semantics="unknown",
                lexical_index=True,
                **common,
            ),
            ExtensionDescriptor(
                "uceg.description.deterministic.edge_synopsis",
                "1.0.0",
                authority="https://taedri.dev/registry",
                applies_to=("relation",),
                wire_type="string",
                missing_value_semantics="unknown",
                lexical_index=True,
            ),
            ExtensionDescriptor(
                "uceg.fingerprint.python.ast_sha256",
                "1.0.0",
                wire_type="digest",
                missing_value_semantics="unknown",
                exact_index=True,
                **common,
            ),
            ExtensionDescriptor(
                "uceg.fingerprint.python.token_simhash64",
                "1.0.0",
                wire_type="hex",
                missing_value_semantics="unknown",
                exact_index=True,
                **common,
            ),
            ExtensionDescriptor(
                "uceg.fingerprint.python.token_minhash16",
                "1.0.0",
                wire_type="structured",
                missing_value_semantics="unknown",
                exact_index=True,
                **common,
            ),
        ]
    )
    return registry
