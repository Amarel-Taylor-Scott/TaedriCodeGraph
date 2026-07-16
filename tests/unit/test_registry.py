from __future__ import annotations

import unittest

from taedri_codegraph.canonical import canonical_digest
from taedri_codegraph.contracts import (
    ExtensionDescriptor,
    FeatureAssertion,
    Modality,
    Polarity,
    ProducerRef,
    SubjectRef,
)
from taedri_codegraph.registry import ExtensionRegistry, RegistryConflictError


class ExtensionRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ExtensionRegistry()
        self.descriptor = ExtensionDescriptor(
            extension_key="org.example.tensor.layout",
            descriptor_version="1.0.0",
            authority="https://example.org/uceg",
            applies_to=("entity",),
            wire_type="string",
            missing_value_semantics="unknown",
            exact_index=True,
        )

    def test_third_party_extension_requires_no_kernel_change(self) -> None:
        self.registry.register(self.descriptor)
        feature = FeatureAssertion.create(
            subject=SubjectRef("entity", "uceg:v1:entity:example"),
            extension_key=self.descriptor.extension_key,
            descriptor_version="1.0.0",
            typed_value="contiguous_c",
            modality=Modality.EXTRACTED,
            polarity=Polarity.POSITIVE,
            producer=ProducerRef("test", "1", canonical_digest({"test": True})),
            evidence_ids=(),
            snapshot_id="uceg:v1:package_snapshot:example",
        )
        self.registry.validate_feature(feature)

    def test_same_version_cannot_be_reinterpreted(self) -> None:
        self.registry.register(self.descriptor)
        changed = ExtensionDescriptor(
            extension_key=self.descriptor.extension_key,
            descriptor_version="1.0.0",
            authority=self.descriptor.authority,
            applies_to=("entity",),
            wire_type="integer",
            missing_value_semantics="unknown",
        )
        with self.assertRaises(RegistryConflictError):
            self.registry.register(changed)

    def test_new_version_is_additive(self) -> None:
        self.registry.register(self.descriptor)
        self.registry.register(
            ExtensionDescriptor(
                extension_key=self.descriptor.extension_key,
                descriptor_version="2.0.0",
                authority=self.descriptor.authority,
                applies_to=("entity", "relation"),
                wire_type="structured",
                missing_value_semantics="unknown",
            )
        )
        self.assertEqual(self.registry.versions(self.descriptor.extension_key), ("1.0.0", "2.0.0"))

    def test_missing_semantics_must_be_explicit(self) -> None:
        with self.assertRaises(ValueError):
            ExtensionDescriptor(
                extension_key="org.example.bad",
                descriptor_version="1.0.0",
                authority="org.example",
                applies_to=("entity",),
                wire_type="string",
                missing_value_semantics="false",
            )


if __name__ == "__main__":
    unittest.main()
