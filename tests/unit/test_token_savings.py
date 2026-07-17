from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.model_providers import (
    ModelUsageReceipt as ProviderModelUsageReceipt,
)
from taedri_codegraph.token_savings import (
    EvidenceIntegrityResult,
    MatchedRunContext,
    ModelUsageReceipt,
    ProofArm,
    RunArmEvidence,
    TokenBreakdown,
    TokenBudget,
    TokenEvidenceClass,
    TokenSavingsError,
    TokenSavingsInput,
    TrustedEvidenceAttestation,
    TrustedEvidenceRequest,
    TrustedEvidenceTrustRoot,
    VerifierReceipt,
    evaluate_token_savings_file,
    load_token_savings_inputs,
    run_spec_digest,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "token-savings"


def digest(label: str) -> str:
    return sha256_digest(label.encode("utf-8"))


TEST_TRUST_KEY = b"token-savings-test-runtime-root-key-v1"
TEST_TRUST_KEY_ID = digest("token-savings-test-runtime-root-key-id")


class ExactTestResolver:
    trust_domain = "tests.token-savings.runtime-store"
    key_id = TEST_TRUST_KEY_ID

    def __init__(
        self,
        mutate_request=None,
        *,
        missing: bool = False,
        signing_key: bytes = TEST_TRUST_KEY,
    ):
        self.mutate_request = mutate_request
        self.missing = missing
        self.signing_key = signing_key

    def resolve(
        self, request: TrustedEvidenceRequest
    ) -> TrustedEvidenceAttestation | None:
        if self.missing:
            return None
        bound = request if self.mutate_request is None else self.mutate_request(request)
        return TrustedEvidenceAttestation.issue_hmac(
            trust_domain=self.trust_domain,
            key_id=self.key_id,
            attestation_ref=digest("trusted-test-attestation"),
            request=bound,
            signing_key=self.signing_key,
        )


class TokenSavingsProofTests(unittest.TestCase):
    def trust_root(self) -> TrustedEvidenceTrustRoot:
        return TrustedEvidenceTrustRoot(
            trust_domain=ExactTestResolver.trust_domain,
            key_id=ExactTestResolver.key_id,
            verification_key=TEST_TRUST_KEY,
        )

    def attested(self, source: TokenSavingsInput):
        return source.evaluate(
            trusted_resolver=ExactTestResolver(),
            trusted_root=self.trust_root(),
        )

    def context(self, **changes: object) -> MatchedRunContext:
        context = MatchedRunContext(
            task_ref=digest("task"),
            seed=41,
            provider_id="provider-a",
            model_id="model-a@exact-revision",
            model_config_digest=digest("model-config"),
            harness_digest=digest("harness"),
            runtime_digest=digest("runtime"),
            policy_digest=digest("policy"),
            oracle_ref=digest("sealed-oracle"),
            snapshot_ref=digest("repository-snapshot"),
            budget=TokenBudget(4, 1_000, 1_000, 10_000, 8, 60_000, 30_000),
        )
        return replace(context, **changes)

    def usage(
        self,
        context: MatchedRunContext,
        arm: ProofArm,
        index: int,
        counts: TokenBreakdown,
        *,
        provider_id: str | None = None,
    ) -> ModelUsageReceipt:
        return ModelUsageReceipt.create(
            run_spec_digest=run_spec_digest(context, arm),
            attempt_index=index,
            provider_id=provider_id or context.provider_id,
            model_id=context.model_id,
            model_config_digest=context.model_config_digest,
            provider_receipt_ref=digest(
                f"{arm.value}:provider-receipt:{index}"
            ),
            provider_content_digest=digest(
                f"{arm.value}:provider-content:{index}"
            ),
            usage_source="unit-test-provider-receipt",
            request_digest=digest(f"{arm.value}:request:{index}"),
            response_digest=digest(f"{arm.value}:response:{index}"),
            tool_calls=1 if counts.tool_tokens else 0,
            usage=counts,
        )

    def resolved_input(
        self,
        *,
        evidence_class: TokenEvidenceClass = TokenEvidenceClass.VERIFIED_REAL_MODEL,
        context: MatchedRunContext | None = None,
        reuse_context: MatchedRunContext | None = None,
        baseline_accepted: bool = True,
        reuse_accepted: bool = True,
        baseline_counts: tuple[TokenBreakdown, ...] | None = None,
        reuse_counts: tuple[TokenBreakdown, ...] | None = None,
        baseline_provider: str | None = None,
        reuse_provider: str | None = None,
        baseline_runner: str = "baseline-model-runner",
        reuse_runner: str = "reuse-model-runner",
        baseline_verifier: str = "independent-matched-verifier",
        reuse_verifier: str = "independent-matched-verifier",
    ) -> TokenSavingsInput:
        base_context = context or self.context()
        treatment_context = reuse_context or base_context
        baseline_values = baseline_counts or (
            TokenBreakdown(60, 20, 10, 20, 5, 2, 3, 4, 1),
            TokenBreakdown(30, 10, 5, 10, 2, 1, 1, 1, 0),
        )
        reuse_values = reuse_counts or (
            TokenBreakdown(50, 20, 5, 15, 2, 2, 3, 4, 1),
        )
        baseline_usage = tuple(
            self.usage(
                base_context,
                ProofArm.BASELINE,
                index,
                counts,
                provider_id=baseline_provider,
            )
            for index, counts in enumerate(baseline_values, start=1)
        )
        reuse_usage = tuple(
            self.usage(
                treatment_context,
                ProofArm.REUSE,
                index,
                counts,
                provider_id=reuse_provider,
            )
            for index, counts in enumerate(reuse_values, start=1)
        )
        baseline_output = digest("baseline-output")
        reuse_output = digest("reuse-output")
        baseline_verification = VerifierReceipt.create(
            run_spec_digest=run_spec_digest(base_context, ProofArm.BASELINE),
            context_digest=base_context.context_digest,
            oracle_ref=base_context.oracle_ref,
            output_digest=baseline_output,
            model_usage_receipt_digests=(item.receipt_digest for item in baseline_usage),
            verifier_id=baseline_verifier,
            source_verifier_ref=digest("baseline-source-verifier-receipt"),
            verifier_config_digest=digest("verifier-config"),
            observed_run_wall_ms=1_000,
            verifier_cpu_ms=100,
            accepted=baseline_accepted,
            tests_total=2,
            tests_passed=2 if baseline_accepted else 1,
            tests_failed=0 if baseline_accepted else 1,
        )
        reuse_verification = VerifierReceipt.create(
            run_spec_digest=run_spec_digest(treatment_context, ProofArm.REUSE),
            context_digest=treatment_context.context_digest,
            oracle_ref=treatment_context.oracle_ref,
            output_digest=reuse_output,
            model_usage_receipt_digests=(item.receipt_digest for item in reuse_usage),
            verifier_id=reuse_verifier,
            source_verifier_ref=digest("reuse-source-verifier-receipt"),
            verifier_config_digest=digest("verifier-config"),
            observed_run_wall_ms=1_000,
            verifier_cpu_ms=100,
            accepted=reuse_accepted,
            tests_total=2,
            tests_passed=2 if reuse_accepted else 1,
            tests_failed=0 if reuse_accepted else 1,
        )
        baseline = RunArmEvidence.create(
            arm=ProofArm.BASELINE,
            context=base_context,
            runner_id=baseline_runner,
            accepted=baseline_accepted,
            output_digest=baseline_output,
            attempt_count=len(baseline_usage),
            model_usage_receipt_digests=(item.receipt_digest for item in baseline_usage),
            verifier_receipt_digest=baseline_verification.receipt_digest,
        )
        reuse = RunArmEvidence.create(
            arm=ProofArm.REUSE,
            context=treatment_context,
            runner_id=reuse_runner,
            accepted=reuse_accepted,
            output_digest=reuse_output,
            attempt_count=len(reuse_usage),
            model_usage_receipt_digests=(item.receipt_digest for item in reuse_usage),
            verifier_receipt_digest=reuse_verification.receipt_digest,
        )
        return TokenSavingsInput.create(
            label="verified matched pair",
            evidence_note=(
                "all model-attempt and independent-verifier receipts are resolved"
            ),
            evidence_class=evidence_class,
            subject_ref=digest("matched-pair-subject"),
            terminal_receipt_refs=tuple(
                sorted((digest("baseline-terminal"), digest("reuse-terminal")))
            ),
            baseline=baseline,
            reuse=reuse,
            model_usage_receipts=(*baseline_usage, *reuse_usage),
            verifier_receipts=(baseline_verification, reuse_verification),
        )

    def historical_input(self) -> TokenSavingsInput:
        context = self.context()
        baseline = RunArmEvidence.create(
            arm=ProofArm.BASELINE,
            context=context,
            runner_id=None,
            accepted=None,
            output_digest=None,
            attempt_count=None,
            reported_total_tokens=137_485,
        )
        reuse = RunArmEvidence.create(
            arm=ProofArm.REUSE,
            context=context,
            runner_id=None,
            accepted=None,
            output_digest=None,
            attempt_count=None,
            reported_total_tokens=85_954,
        )
        return TokenSavingsInput.create(
            label="historical reported total",
            evidence_note="raw model usage and verifier evidence was not retained",
            evidence_class=TokenEvidenceClass.REPORTED_HISTORICAL,
            subject_ref=digest("historical-subject"),
            terminal_receipt_refs=(digest("historical-report"),),
            baseline=baseline,
            reuse=reuse,
            model_usage_receipts=(),
            verifier_receipts=(),
        )

    def recreate_run(self, run: RunArmEvidence, **changes: object) -> RunArmEvidence:
        values = {
            "arm": run.arm,
            "context": run.context,
            "runner_id": run.runner_id,
            "accepted": run.accepted,
            "output_digest": run.output_digest,
            "attempt_count": run.attempt_count,
            "model_usage_receipt_digests": run.model_usage_receipt_digests,
            "verifier_receipt_digest": run.verifier_receipt_digest,
            "reported_total_tokens": run.reported_total_tokens,
        }
        values.update(changes)
        return RunArmEvidence.create(**values)  # type: ignore[arg-type]

    def recreate_source(
        self, source: TokenSavingsInput, **changes: object
    ) -> TokenSavingsInput:
        values = {
            "label": source.label,
            "evidence_note": source.evidence_note,
            "evidence_class": source.evidence_class,
            "subject_ref": source.subject_ref,
            "terminal_receipt_refs": source.terminal_receipt_refs,
            "baseline": source.baseline,
            "reuse": source.reuse,
            "model_usage_receipts": source.model_usage_receipts,
            "verifier_receipts": source.verifier_receipts,
        }
        values.update(changes)
        return TokenSavingsInput.create(**values)  # type: ignore[arg-type]

    def test_verified_pair_accounts_every_category_and_claims_exact_savings(self) -> None:
        source = self.resolved_input()
        first = self.attested(source)
        second = self.attested(source)
        self.assertEqual(first.proof_digest, second.proof_digest)
        self.assertEqual(first.baseline_total_tokens, 155)
        self.assertEqual(first.reuse_total_tokens, 82)
        self.assertEqual(first.token_savings, 73)
        self.assertEqual(first.token_savings_ppm, 470_967)
        self.assertTrue(first.receipt_integrity_resolved)
        self.assertTrue(first.attempts_complete)
        self.assertTrue(first.correctness_preserving)
        self.assertTrue(first.evidence_integrity_verified)
        self.assertTrue(first.savings_claimable)
        self.assertIsNone(first.claim_reason)
        self.assertRegex(first.proof_digest, r"^sha256:[0-9a-f]{64}$")
        assert first.baseline_tokens is not None
        self.assertEqual(first.baseline_tokens.cached_prompt_tokens, 30)
        self.assertEqual(first.baseline_tokens.uncached_prompt_tokens, 60)

    def test_live_provider_receipt_adapter_and_matched_pair_builder(self) -> None:
        context = self.context()
        provider_receipt = ProviderModelUsageReceipt.create(
            provider_id=context.provider_id,
            provider_api="test-chat-v1",
            usage_source="test-response",
            endpoint_origin="https://provider.invalid",
            model_requested=context.model_id,
            model_reported=context.model_id,
            request_digest=digest("live-request"),
            response_digest=digest("live-response"),
            content_digest=digest("live-content"),
            started_at="2026-07-16T12:00:00+00:00",
            completed_at="2026-07-16T12:00:01+00:00",
            wall_ms=1_000,
            prompt_tokens=50,
            completion_tokens=15,
            total_duration_ns=None,
            load_duration_ns=None,
            prompt_eval_duration_ns=None,
            eval_duration_ns=None,
            finish_reason="stop",
        )
        adapted = ModelUsageReceipt.from_provider_receipt(
            context=context,
            arm=ProofArm.BASELINE,
            attempt_index=1,
            provider_receipt=provider_receipt,
            cached_prompt_tokens=20,
            reasoning_tokens=5,
            tool_tokens=2,
            selector_tokens=2,
            retrieval_tokens=3,
            verification_tokens=4,
            repair_tokens=1,
            tool_calls=1,
        )
        self.assertEqual(adapted.usage.accounted_total_tokens, 82)
        self.assertEqual(adapted.request_digest, provider_receipt.request_digest)
        self.assertEqual(adapted.provider_receipt_ref, provider_receipt.identity.id)
        self.assertEqual(
            adapted.provider_content_digest, provider_receipt.content_digest
        )
        self.assertEqual(adapted.usage_source, provider_receipt.usage_source)
        with self.assertRaisesRegex(TokenSavingsError, "content-addressed identity"):
            ModelUsageReceipt.from_provider_receipt(
                context=context,
                arm=ProofArm.BASELINE,
                attempt_index=1,
                provider_receipt=replace(provider_receipt, prompt_tokens=51),
            )

        manual = self.resolved_input(context=context)
        baseline_usages = manual.model_usage_receipts[:2]
        reuse_usages = manual.model_usage_receipts[2:]
        baseline_verifier = VerifierReceipt.for_run(
            context=context,
            arm=ProofArm.BASELINE,
            model_usage_receipts=baseline_usages,
            output_digest=manual.baseline.output_digest or "",
            verifier_id="independent-matched-verifier",
            source_verifier_ref=digest("baseline-source-verifier-receipt"),
            verifier_config_digest=digest("verifier-config"),
            observed_run_wall_ms=1_000,
            verifier_cpu_ms=100,
            accepted=True,
            tests_total=2,
            tests_passed=2,
            tests_failed=0,
        )
        built = TokenSavingsInput.create_matched_pair(
            label="verified matched pair",
            evidence_note=(
                "all model-attempt and independent-verifier receipts are resolved"
            ),
            subject_ref=manual.subject_ref,
            terminal_receipt_refs=manual.terminal_receipt_refs,
            context=context,
            baseline_runner_id="baseline-model-runner",
            baseline_attempt_count=2,
            baseline_model_usage_receipts=baseline_usages,
            baseline_verifier_receipt=baseline_verifier,
            reuse_runner_id="reuse-model-runner",
            reuse_attempt_count=1,
            reuse_model_usage_receipts=reuse_usages,
            reuse_verifier_receipt=manual.verifier_receipts[1],
        )
        self.assertIs(
            built.evidence_class, TokenEvidenceClass.CONFORMANCE_FIXTURE
        )
        self.assertFalse(built.evaluate().savings_claimable)
        real_built = TokenSavingsInput.create(
            label=built.label,
            evidence_note=built.evidence_note,
            evidence_class=TokenEvidenceClass.VERIFIED_REAL_MODEL,
            subject_ref=built.subject_ref,
            terminal_receipt_refs=built.terminal_receipt_refs,
            baseline=built.baseline,
            reuse=built.reuse,
            model_usage_receipts=built.model_usage_receipts,
            verifier_receipts=built.verifier_receipts,
        )
        self.assertEqual(
            self.attested(real_built).proof_digest,
            self.attested(manual).proof_digest,
        )
        with self.assertRaisesRegex(TokenSavingsError, "selectively omitted"):
            TokenSavingsInput.create_matched_pair(
                label="invalid omission",
                evidence_note="attempt count disagrees with supplied receipts",
                subject_ref=manual.subject_ref,
                terminal_receipt_refs=manual.terminal_receipt_refs,
                context=context,
                baseline_runner_id="baseline-model-runner",
                baseline_attempt_count=3,
                baseline_model_usage_receipts=baseline_usages,
                baseline_verifier_receipt=baseline_verifier,
                reuse_runner_id="reuse-model-runner",
                reuse_attempt_count=1,
                reuse_model_usage_receipts=reuse_usages,
                reuse_verifier_receipt=manual.verifier_receipts[1],
                evidence_class=TokenEvidenceClass.VERIFIED_REAL_MODEL,
            )

    def test_cached_prompt_tokens_are_a_reported_subset_not_double_counted(self) -> None:
        counts = TokenBreakdown(100, 90, 0, 10, 0, 0, 0, 0, 0)
        self.assertEqual(counts.uncached_prompt_tokens, 10)
        self.assertEqual(counts.accounted_total_tokens, 110)
        proof = self.resolved_input(
            baseline_counts=(counts,),
            reuse_counts=(TokenBreakdown(90, 80, 0, 10, 0, 0, 0, 0, 0),),
        ).evaluate()
        self.assertEqual(proof.baseline_total_tokens, 110)
        self.assertEqual(proof.reuse_total_tokens, 100)

    def test_synthetic_conformance_receipts_resolve_but_never_claim_efficacy(self) -> None:
        proof = self.resolved_input(
            evidence_class=TokenEvidenceClass.CONFORMANCE_FIXTURE
        ).evaluate()
        self.assertTrue(proof.receipt_integrity_resolved)
        self.assertTrue(proof.attempts_complete)
        self.assertFalse(proof.evidence_integrity_verified)
        self.assertFalse(proof.correctness_preserving)
        self.assertFalse(proof.savings_claimable)
        self.assertIn("synthetic conformance", proof.claim_reason or "")

    def test_historical_137485_to_85954_is_arithmetic_not_verified_evidence(self) -> None:
        proof = self.historical_input().evaluate()
        self.assertEqual(proof.baseline_total_tokens, 137_485)
        self.assertEqual(proof.reuse_total_tokens, 85_954)
        self.assertEqual(proof.token_savings, 51_531)
        self.assertEqual(proof.token_savings_ppm, 374_811)
        self.assertFalse(proof.receipt_integrity_resolved)
        self.assertFalse(proof.attempts_complete)
        self.assertIsNone(proof.paired_acceptance)
        self.assertFalse(proof.savings_claimable)
        self.assertIn("lack raw", proof.claim_reason or "")

    def test_every_matched_context_field_must_be_exact(self) -> None:
        base = self.context()
        cases = {
            "task_ref": {"task_ref": digest("another-task")},
            "seed": {"seed": 42},
            "provider_id": {"provider_id": "provider-b"},
            "model_id": {"model_id": "model-b"},
            "model_config_digest": {"model_config_digest": digest("config-b")},
            "harness_digest": {"harness_digest": digest("harness-b")},
            "runtime_digest": {"runtime_digest": digest("runtime-b")},
            "policy_digest": {"policy_digest": digest("policy-b")},
            "oracle_ref": {"oracle_ref": digest("oracle-b")},
            "snapshot_ref": {"snapshot_ref": digest("snapshot-b")},
            "budget": {"budget": replace(base.budget, max_total_tokens=9_999)},
        }
        for name, changes in cases.items():
            with self.subTest(name=name):
                source = self.resolved_input(
                    context=base, reuse_context=replace(base, **changes)
                )
                with self.assertRaisesRegex(TokenSavingsError, name):
                    source.evaluate()

    def test_selective_attempt_omission_and_unassigned_receipts_fail_closed(self) -> None:
        source = self.resolved_input()
        omitted = self.recreate_run(source.baseline, attempt_count=3)
        with self.assertRaisesRegex(TokenSavingsError, "selectively omitted"):
            self.recreate_source(source, baseline=omitted).evaluate()
        extra = self.usage(
            source.baseline.context,
            ProofArm.BASELINE,
            99,
            TokenBreakdown(1, 0, 0, 0, 0, 0, 0, 0, 0),
        )
        with self.assertRaisesRegex(TokenSavingsError, "unassigned attempts"):
            self.recreate_source(
                source,
                model_usage_receipts=(*source.model_usage_receipts, extra),
            ).evaluate()

    def test_missing_usage_or_verifier_receipt_fails_closed(self) -> None:
        source = self.resolved_input()
        with self.assertRaisesRegex(TokenSavingsError, "unresolved model usage"):
            self.recreate_source(
                source, model_usage_receipts=source.model_usage_receipts[1:]
            ).evaluate()
        with self.assertRaisesRegex(TokenSavingsError, "unresolved verifier"):
            self.recreate_source(
                source, verifier_receipts=source.verifier_receipts[1:]
            ).evaluate()

    def test_attempt_indices_must_be_contiguous_and_provider_must_match(self) -> None:
        source = self.resolved_input(
            baseline_counts=(TokenBreakdown(10, 0, 0, 1, 0, 0, 0, 0, 0),),
        )
        original = source.model_usage_receipts[0]
        noncontiguous = ModelUsageReceipt.create(
            run_spec_digest=original.run_spec_digest,
            attempt_index=2,
            provider_id=original.provider_id,
            model_id=original.model_id,
            model_config_digest=original.model_config_digest,
            provider_receipt_ref=original.provider_receipt_ref,
            provider_content_digest=original.provider_content_digest,
            usage_source=original.usage_source,
            request_digest=original.request_digest,
            response_digest=original.response_digest,
            tool_calls=original.tool_calls,
            usage=original.usage,
        )
        verifier = source.verifier_receipts[0]
        replacement_verifier = VerifierReceipt.create(
            run_spec_digest=verifier.run_spec_digest,
            context_digest=verifier.context_digest,
            oracle_ref=verifier.oracle_ref,
            output_digest=verifier.output_digest,
            model_usage_receipt_digests=(noncontiguous.receipt_digest,),
            verifier_id=verifier.verifier_id,
            source_verifier_ref=verifier.source_verifier_ref,
            verifier_config_digest=verifier.verifier_config_digest,
            observed_run_wall_ms=verifier.observed_run_wall_ms,
            verifier_cpu_ms=verifier.verifier_cpu_ms,
            accepted=True,
            tests_total=2,
            tests_passed=2,
            tests_failed=0,
        )
        run = self.recreate_run(
            source.baseline,
            model_usage_receipt_digests=(noncontiguous.receipt_digest,),
            verifier_receipt_digest=replacement_verifier.receipt_digest,
        )
        modified = self.recreate_source(
            source,
            baseline=run,
            model_usage_receipts=(noncontiguous, *source.model_usage_receipts[1:]),
            verifier_receipts=(replacement_verifier, source.verifier_receipts[1]),
        )
        with self.assertRaisesRegex(TokenSavingsError, "contiguous"):
            modified.evaluate()
        with self.assertRaisesRegex(TokenSavingsError, "provider/model/config"):
            self.resolved_input(baseline_provider="provider-b").evaluate()

    def test_verifier_must_cover_exact_attempts_output_oracle_and_independence(self) -> None:
        source = self.resolved_input()
        verifier = source.verifier_receipts[0]
        cases = {
            "attempt set": {
                "model_usage_receipt_digests": verifier.model_usage_receipt_digests[:1]
            },
            "another output": {"output_digest": digest("wrong-output")},
            "another oracle": {"oracle_ref": digest("wrong-oracle")},
            "not independent": {"verifier_id": source.baseline.runner_id},
        }
        for expected, changes in cases.items():
            with self.subTest(expected=expected):
                values = {
                    "run_spec_digest": verifier.run_spec_digest,
                    "context_digest": verifier.context_digest,
                    "oracle_ref": verifier.oracle_ref,
                    "output_digest": verifier.output_digest,
                    "model_usage_receipt_digests": verifier.model_usage_receipt_digests,
                    "verifier_id": verifier.verifier_id,
                    "source_verifier_ref": verifier.source_verifier_ref,
                    "verifier_config_digest": verifier.verifier_config_digest,
                    "observed_run_wall_ms": verifier.observed_run_wall_ms,
                    "verifier_cpu_ms": verifier.verifier_cpu_ms,
                    "accepted": verifier.accepted,
                    "tests_total": verifier.tests_total,
                    "tests_passed": verifier.tests_passed,
                    "tests_failed": verifier.tests_failed,
                }
                values.update(changes)
                replacement_verifier = VerifierReceipt.create(**values)  # type: ignore[arg-type]
                baseline = self.recreate_run(
                    source.baseline,
                    verifier_receipt_digest=replacement_verifier.receipt_digest,
                )
                modified = self.recreate_source(
                    source,
                    baseline=baseline,
                    verifier_receipts=(replacement_verifier, source.verifier_receipts[1]),
                )
                with self.assertRaisesRegex(TokenSavingsError, expected):
                    modified.evaluate()

    def test_unequal_acceptance_and_equal_rejection_fail_closed(self) -> None:
        with self.assertRaisesRegex(TokenSavingsError, "unequal independent acceptance"):
            self.resolved_input(reuse_accepted=False).evaluate()
        with self.assertRaisesRegex(TokenSavingsError, "both matched arms"):
            self.resolved_input(
                baseline_accepted=False, reuse_accepted=False
            ).evaluate()

    def test_no_savings_or_budget_overrun_cannot_claim(self) -> None:
        counts = TokenBreakdown(20, 0, 0, 5, 0, 0, 0, 0, 0)
        proof = self.resolved_input(
            baseline_counts=(counts,), reuse_counts=(counts,)
        ).evaluate()
        self.assertEqual(proof.token_savings, 0)
        self.assertFalse(proof.savings_claimable)
        constrained = replace(self.context().budget, max_total_tokens=20)
        with self.assertRaisesRegex(TokenSavingsError, "total token budget"):
            self.resolved_input(context=replace(self.context(), budget=constrained)).evaluate()
        budget_cases = {
            "tool-call budget": replace(
                self.context().budget, max_tool_calls=0
            ),
            "wall-time budget": replace(
                self.context().budget, max_wall_ms=999
            ),
            "verifier-CPU budget": replace(
                self.context().budget, max_verifier_cpu_ms=99
            ),
        }
        for expected, budget in budget_cases.items():
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(TokenSavingsError, expected):
                    self.resolved_input(
                        context=replace(self.context(), budget=budget)
                    ).evaluate()

    def test_malformed_refs_cached_overlap_and_content_digest_tampering_fail(self) -> None:
        with self.assertRaisesRegex(TokenSavingsError, "cached_prompt_tokens"):
            TokenBreakdown(9, 10, 0, 0, 0, 0, 0, 0, 0)
        with self.assertRaisesRegex(TokenSavingsError, "exact sha256"):
            replace(self.context(), model_config_digest="sha256:x")
        raw = self.resolved_input().to_dict()
        raw["model_usage_receipts"][0]["usage"]["prompt_tokens"] += 1  # type: ignore[index]
        with self.assertRaisesRegex(TokenSavingsError, "content digest"):
            TokenSavingsInput.from_dict(raw)
        source = self.resolved_input()
        first = source.model_usage_receipts[0]
        in_memory_tamper = replace(
            first,
            usage=replace(first.usage, prompt_tokens=first.usage.prompt_tokens + 1),
        )
        with self.assertRaisesRegex(TokenSavingsError, "content digest"):
            replace(
                source,
                model_usage_receipts=(
                    in_memory_tamper,
                    *source.model_usage_receipts[1:],
                ),
            ).evaluate()

    def test_loader_rejects_unknown_fields_unmatched_arms_and_invalid_json(self) -> None:
        raw = self.resolved_input().to_dict()
        raw["unexpected"] = True
        with self.assertRaisesRegex(TokenSavingsError, "extra=unexpected"):
            TokenSavingsInput.from_dict(raw)
        source = self.resolved_input()
        with self.assertRaisesRegex(TokenSavingsError, "baseline input"):
            self.recreate_source(source, baseline=source.reuse).evaluate()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("{not json", "utf-8")
            with self.assertRaisesRegex(TokenSavingsError, "invalid token-savings JSON"):
                load_token_savings_inputs(path)

    def test_json_and_jsonl_loaders_and_cli_emit_canonical_proofs(self) -> None:
        value = self.resolved_input(
            evidence_class=TokenEvidenceClass.CONFORMANCE_FIXTURE
        ).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "proof.json"
            jsonl_path = root / "proof.jsonl"
            json_path.write_text(json.dumps(value), "utf-8")
            jsonl_path.write_text(json.dumps(value) + "\n" + json.dumps(value) + "\n", "utf-8")
            self.assertEqual(len(evaluate_token_savings_file(json_path)), 1)
            self.assertEqual(len(evaluate_token_savings_file(jsonl_path)), 2)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "prove_token_savings.py"),
                    str(json_path),
                    "--compact",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            self.assertFalse(output["savings_claimable"])
            self.assertRegex(output["proof_digest"], r"^sha256:[0-9a-f]{64}$")
            output_path = root / "emitted-proof.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "prove_token_savings.py"),
                    str(json_path),
                    "--compact",
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(json.loads(output_path.read_text("utf-8")), output)

    def test_json_evidence_label_cannot_self_promote(self) -> None:
        conformance = self.resolved_input(
            evidence_class=TokenEvidenceClass.CONFORMANCE_FIXTURE
        )
        label_flip = conformance.to_dict()
        label_flip["evidence_class"] = TokenEvidenceClass.VERIFIED_REAL_MODEL.value
        with self.assertRaisesRegex(TokenSavingsError, "content digest"):
            TokenSavingsInput.from_dict(label_flip)

        self_hashed_fake = TokenSavingsInput.create(
            label=conformance.label,
            evidence_note=conformance.evidence_note,
            evidence_class=TokenEvidenceClass.VERIFIED_REAL_MODEL,
            subject_ref=conformance.subject_ref,
            terminal_receipt_refs=conformance.terminal_receipt_refs,
            baseline=conformance.baseline,
            reuse=conformance.reuse,
            model_usage_receipts=conformance.model_usage_receipts,
            verifier_receipts=conformance.verifier_receipts,
        )
        proof = TokenSavingsInput.from_dict(self_hashed_fake.to_dict()).evaluate()
        self.assertFalse(proof.evidence_integrity_verified)
        self.assertFalse(proof.savings_claimable)
        self.assertIn("configured runtime trust root", proof.claim_reason or "")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "self-hashed-fake-real.json"
            path.write_text(json.dumps(self_hashed_fake.to_dict()), "utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "prove_token_savings.py"),
                    str(path),
                    "--compact",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(json.loads(completed.stdout)["savings_claimable"])

    def test_trusted_attestation_binds_every_exact_reference(self) -> None:
        source = self.resolved_input()
        missing = source.evaluate(
            trusted_resolver=ExactTestResolver(missing=True),
            trusted_root=self.trust_root(),
        )
        self.assertFalse(missing.savings_claimable)
        self.assertIsNone(missing.attestation_ref)

        def changed_refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
            return tuple(sorted((*values[1:], digest(label))))

        cases = {
            "source": lambda request: replace(
                request, source_digest=digest("wrong-source")
            ),
            "context": lambda request: replace(
                request, context_digest=digest("wrong-context")
            ),
            "pair": lambda request: replace(
                request, baseline_run_digest=digest("wrong-pair")
            ),
            "missing provider": lambda request: replace(
                request,
                provider_receipt_refs=request.provider_receipt_refs[1:],
            ),
            "wrong provider": lambda request: replace(
                request,
                provider_receipt_refs=changed_refs(
                    request.provider_receipt_refs, "wrong-provider"
                ),
            ),
            "extra provider": lambda request: replace(
                request,
                provider_receipt_refs=tuple(
                    sorted((*request.provider_receipt_refs, digest("extra-provider")))
                ),
            ),
            "wrong usage receipt": lambda request: replace(
                request,
                model_usage_receipt_digests=changed_refs(
                    request.model_usage_receipt_digests, "wrong-usage-receipt"
                ),
            ),
            "wrong verifier": lambda request: replace(
                request,
                source_verifier_refs=changed_refs(
                    request.source_verifier_refs, "wrong-verifier"
                ),
            ),
            "extra verifier receipt": lambda request: replace(
                request,
                verifier_receipt_digests=tuple(
                    sorted(
                        (
                            *request.verifier_receipt_digests,
                            digest("extra-verifier-receipt"),
                        )
                    )
                ),
            ),
            "missing terminal": lambda request: replace(
                request,
                terminal_receipt_refs=request.terminal_receipt_refs[1:],
            ),
            "extra terminal": lambda request: replace(
                request,
                terminal_receipt_refs=tuple(
                    sorted((*request.terminal_receipt_refs, digest("extra-terminal")))
                ),
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(TokenSavingsError, "exact proof source"):
                    source.evaluate(
                        trusted_resolver=ExactTestResolver(mutate),
                        trusted_root=self.trust_root(),
                    )

    def test_resolver_or_forged_attestation_cannot_supply_its_own_trust(self) -> None:
        source = self.resolved_input()

        resolver_only = source.evaluate(
            trusted_resolver=ExactTestResolver()
        )
        self.assertFalse(resolver_only.evidence_integrity_verified)
        self.assertFalse(resolver_only.savings_claimable)
        self.assertIsNone(resolver_only.trust_domain)
        self.assertIn("configured runtime trust root", resolver_only.claim_reason or "")

        attacker_key = b"attacker-controlled-runtime-root-key-v1"
        with self.assertRaisesRegex(TokenSavingsError, "not authenticated"):
            source.evaluate(
                trusted_resolver=ExactTestResolver(signing_key=attacker_key),
                trusted_root=self.trust_root(),
            )
        for changed_root in (
            replace(self.trust_root(), trust_domain="tests.another-domain"),
            replace(self.trust_root(), key_id=digest("another-trust-key-id")),
        ):
            with self.assertRaisesRegex(TokenSavingsError, "configured trust root"):
                source.evaluate(
                    trusted_resolver=ExactTestResolver(),
                    trusted_root=changed_root,
                )

        # There is intentionally no public unkeyed attestation constructor.  A
        # valid-looking content digest from a structural resolver is not authority.
        self.assertFalse(hasattr(TrustedEvidenceAttestation, "create"))
        root = self.trust_root()
        self.assertNotIn(TEST_TRUST_KEY.decode("ascii"), repr(root))
        self.assertFalse(hasattr(root, "to_dict"))
        self.assertNotIn(
            TEST_TRUST_KEY.decode("ascii"),
            json.dumps(self.attested(source).to_dict(), sort_keys=True),
        )

    def test_matched_verifier_occurrences_and_conditions_are_exact(self) -> None:
        source = self.resolved_input()
        baseline_verifier, reuse_verifier = source.verifier_receipts

        cases = {
            "cloned source receipt": {
                "source_verifier_ref": baseline_verifier.source_verifier_ref,
            },
            "verifier_id": {"verifier_id": "different-verifier-runtime"},
            "verifier_config_digest": {
                "verifier_config_digest": digest("different-verifier-config")
            },
            "tests_total": {
                "tests_total": 7,
                "tests_passed": 7,
                "tests_failed": 0,
            },
        }
        for expected, changes in cases.items():
            with self.subTest(expected=expected):
                values = {
                    "run_spec_digest": reuse_verifier.run_spec_digest,
                    "context_digest": reuse_verifier.context_digest,
                    "oracle_ref": reuse_verifier.oracle_ref,
                    "output_digest": reuse_verifier.output_digest,
                    "model_usage_receipt_digests": (
                        reuse_verifier.model_usage_receipt_digests
                    ),
                    "verifier_id": reuse_verifier.verifier_id,
                    "source_verifier_ref": reuse_verifier.source_verifier_ref,
                    "verifier_config_digest": (
                        reuse_verifier.verifier_config_digest
                    ),
                    "observed_run_wall_ms": (
                        reuse_verifier.observed_run_wall_ms
                    ),
                    "verifier_cpu_ms": reuse_verifier.verifier_cpu_ms,
                    "accepted": reuse_verifier.accepted,
                    "tests_total": reuse_verifier.tests_total,
                    "tests_passed": reuse_verifier.tests_passed,
                    "tests_failed": reuse_verifier.tests_failed,
                }
                values.update(changes)
                replacement = VerifierReceipt.create(**values)  # type: ignore[arg-type]
                reuse_run = self.recreate_run(
                    source.reuse,
                    verifier_receipt_digest=replacement.receipt_digest,
                )
                attacked = self.recreate_source(
                    source,
                    reuse=reuse_run,
                    verifier_receipts=(baseline_verifier, replacement),
                )
                with self.assertRaisesRegex(TokenSavingsError, expected):
                    attacked.evaluate()

    def test_cloned_provider_source_receipts_fail_closed(self) -> None:
        source = self.resolved_input(
            baseline_counts=(TokenBreakdown(20, 0, 0, 5, 0, 0, 0, 0, 0),),
            reuse_counts=(TokenBreakdown(10, 0, 0, 5, 0, 0, 0, 0, 0),),
        )
        baseline_usage, reuse_usage = source.model_usage_receipts
        cloned_usage = ModelUsageReceipt.create(
            run_spec_digest=reuse_usage.run_spec_digest,
            attempt_index=reuse_usage.attempt_index,
            provider_id=reuse_usage.provider_id,
            model_id=reuse_usage.model_id,
            model_config_digest=reuse_usage.model_config_digest,
            provider_receipt_ref=baseline_usage.provider_receipt_ref,
            provider_content_digest=reuse_usage.provider_content_digest,
            usage_source=reuse_usage.usage_source,
            request_digest=reuse_usage.request_digest,
            response_digest=reuse_usage.response_digest,
            tool_calls=reuse_usage.tool_calls,
            usage=reuse_usage.usage,
        )
        reuse_verifier = source.verifier_receipts[1]
        verifier_for_clone = VerifierReceipt.create(
            run_spec_digest=reuse_verifier.run_spec_digest,
            context_digest=reuse_verifier.context_digest,
            oracle_ref=reuse_verifier.oracle_ref,
            output_digest=reuse_verifier.output_digest,
            model_usage_receipt_digests=(cloned_usage.receipt_digest,),
            verifier_id=reuse_verifier.verifier_id,
            source_verifier_ref=reuse_verifier.source_verifier_ref,
            verifier_config_digest=reuse_verifier.verifier_config_digest,
            observed_run_wall_ms=reuse_verifier.observed_run_wall_ms,
            verifier_cpu_ms=reuse_verifier.verifier_cpu_ms,
            accepted=True,
            tests_total=2,
            tests_passed=2,
            tests_failed=0,
        )
        cloned_run = self.recreate_run(
            source.reuse,
            model_usage_receipt_digests=(cloned_usage.receipt_digest,),
            verifier_receipt_digest=verifier_for_clone.receipt_digest,
        )
        cloned_source = TokenSavingsInput.create(
            label=source.label,
            evidence_note=source.evidence_note,
            evidence_class=source.evidence_class,
            subject_ref=source.subject_ref,
            terminal_receipt_refs=source.terminal_receipt_refs,
            baseline=source.baseline,
            reuse=cloned_run,
            model_usage_receipts=(baseline_usage, cloned_usage),
            verifier_receipts=(source.verifier_receipts[0], verifier_for_clone),
        )
        with self.assertRaisesRegex(TokenSavingsError, "cloned source receipt"):
            cloned_source.evaluate()

    def test_integrity_result_is_explicit_bound_and_real_only(self) -> None:
        proof = self.attested(self.resolved_input())
        result = proof.integrity_result()
        self.assertTrue(result.verified)
        self.assertEqual(result.subject_ref, proof.subject_ref)
        self.assertEqual(result.covered_receipt_refs, proof.terminal_receipt_refs)
        self.assertEqual(result.provider_receipt_refs, proof.provider_receipt_refs)
        self.assertEqual(result.source_verifier_refs, proof.source_verifier_refs)
        with self.assertRaises(TypeError):
            proof.integrity_result(  # type: ignore[call-arg]
                subject_ref=digest("arbitrary-subject")
            )

    def test_checked_fixtures_are_labeled_and_non_claimable(self) -> None:
        synthetic = evaluate_token_savings_file(
            FIXTURES / "synthetic-conformance.json"
        )[0]
        historical = evaluate_token_savings_file(
            FIXTURES / "reported-historical-137485-to-85954.json"
        )[0]
        self.assertIs(synthetic.evidence_class, TokenEvidenceClass.CONFORMANCE_FIXTURE)
        self.assertFalse(synthetic.savings_claimable)
        self.assertIs(historical.evidence_class, TokenEvidenceClass.REPORTED_HISTORICAL)
        self.assertEqual(historical.token_savings, 51_531)
        self.assertFalse(historical.evidence_integrity_verified)


if __name__ == "__main__":
    unittest.main()
