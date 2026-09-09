"""The reviewed OpenAI gate converts only into a partial, score-inert seed."""

from __future__ import annotations

import base64
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Brief, Critique, canonical_bytes, digest
from mos_eisley.core.protocol import Effort, Usage
from mos_eisley.core.skills import PromptAsset
from mos_eisley.evaluation.execution import (
    EvaluationRequest,
    ExecutionBatch,
    RawResultSet,
)
from mos_eisley.evaluation.models import RouteCandidate
from mos_eisley.run.broker_audit import AssignmentAuthorization
from mos_eisley.run.brokered_evaluation import BrokeredEvaluationArtifact
from mos_eisley.run.evaluation_conformance import (
    AuthenticatedEvaluationConformance,
    EvaluationConformanceObservation,
    EvaluationConformanceSignature,
    SignedEvaluationConformanceObservation,
)
from mos_eisley.run.openai_conformance_conversion import (
    OpenAIConformanceCalibrationSeed,
    OpenAIConformanceConversionPolicy,
    OpenAIConformanceProfileRequirement,
    convert_openai_conformance_to_calibration_seed,
)
from mos_eisley.run.store import private_write

PROFILES: tuple[tuple[str, Effort, tuple[str, str, str]], ...] = (
    ("gpt-5.6-luna", "low", ("luna-low-1", "luna-low-2", "luna-low-3")),
    (
        "gpt-5.6-sol",
        "high",
        ("sol-high-historical-1", "sol-high-2", "sol-high-3"),
    ),
    (
        "gpt-5.6-sol",
        "medium",
        ("sol-medium-1", "sol-medium-2", "sol-medium-3"),
    ),
    (
        "gpt-5.6-terra",
        "medium",
        ("terra-medium-1", "terra-medium-2", "terra-medium-3"),
    ),
    (
        "gpt-6-astra",
        "high",
        ("astra-high-1", "astra-high-2", "astra-high-3"),
    ),
    (
        "gpt-6-astra",
        "max",
        ("astra-max-1", "astra-max-2", "astra-max-3"),
    ),
)


def _sha(label: str) -> str:
    return digest(label.encode())


def conversion_inputs() -> tuple[
    ExecutionBatch,
    bytes,
    OpenAIConformanceConversionPolicy,
    tuple[AuthenticatedEvaluationConformance, ...],
    tuple[BrokeredEvaluationArtifact, ...],
]:
    plan_sha256 = _sha("plan")
    requests: list[EvaluationRequest] = []
    positions: list[tuple[str, str, Effort, EvaluationRequest]] = []
    index = 0
    for model, effort, profile_positions in PROFILES:
        route = RouteCandidate(
            backend="api",
            provider="openai",
            model=model,
            effort=effort,
            client_version="openai/2.54.0",
            registry_sha256=_sha("registry"),
            prompt=PromptAsset(mode="inline", instructions="Review the change."),
        )
        for position in profile_positions:
            request = EvaluationRequest(
                sample_id=_sha(f"sample-{index}"),
                route=route,
                brief=Brief(spec="Return a structured review.", diff=f"change {index}"),
            )
            requests.append(request)
            positions.append((position, model, effort, request))
            index += 1
    requests.append(
        EvaluationRequest(
            sample_id=_sha("unconverted-sample"),
            route=requests[0].route,
            brief=Brief(spec="Remain outside the seed.", diff="unconverted change"),
        )
    )
    batch = ExecutionBatch(plan_sha256=plan_sha256, requests=tuple(requests))
    receipts: list[AuthenticatedEvaluationConformance] = []
    artifacts: list[BrokeredEvaluationArtifact] = []
    successes: list[dict[str, object]] = []
    observed_at = datetime(2026, 9, 9, tzinfo=UTC)
    signature = base64.b64encode(b"s" * 64).decode()
    for offset, (position, model, effort, request) in enumerate(positions):
        authorization = AssignmentAuthorization(
            plan_sha256=batch.plan_sha256,
            batch_sha256=batch.batch_sha256,
            sample_id=request.sample_id,
            candidate_id=request.route.candidate_id,
            evaluation_request_sha256=request.request_sha256,
            provider_request_sha256=_sha(f"provider-request-{offset}"),
            spend_policy_sha256=_sha(f"spend-policy-{offset}"),
            ledger_id=_sha(f"ledger-{offset // 5}"),
            ledger_entry_id=_sha(f"ledger-entry-{offset}"),
        )
        artifact = BrokeredEvaluationArtifact(
            authorization=authorization,
            authorization_sha256=digest(canonical_bytes(authorization)),
            outcome_sha256=_sha(f"outcome-{offset}"),
            provider_response_sha256=_sha(f"response-{offset}"),
            provider_request_id=f"resp_{offset}",
            usage=Usage(
                unit="tokens",
                input=100 + offset,
                output=20,
                reasoning=10,
                cache_read=0,
            ),
            latency_ms=1000 + offset,
            cost_microusd=100 + offset,
            critique=Critique(),
        )
        observation = EvaluationConformanceObservation(
            conformance_policy_sha256=_sha(f"conformance-policy-{offset}"),
            plan_sha256=batch.plan_sha256,
            batch_sha256=batch.batch_sha256,
            sample_id=request.sample_id,
            candidate_id=request.route.candidate_id,
            evaluation_request_sha256=request.request_sha256,
            provider_request_sha256=authorization.provider_request_sha256,
            spend_policy_sha256=authorization.spend_policy_sha256,
            ledger_id=authorization.ledger_id,
            ledger_entry_id=authorization.ledger_entry_id,
            artifact_sha256=artifact.artifact_sha256,
            authorization_sha256=artifact.authorization_sha256,
            outcome_sha256=artifact.outcome_sha256,
            provider_response_sha256=artifact.provider_response_sha256 or _sha("none"),
            provider_request_id=artifact.provider_request_id or "missing",
            model=model,
            effort=effort,
            usage=artifact.usage or Usage(unit="tokens", input=0, output=0),
            latency_ms=artifact.latency_ms or 0,
            cost_microusd=artifact.cost_microusd or 0,
            observed_at=observed_at,
            sdk_version="2.54.0",
            transport_evidence_sha256=artifact.provider_response_sha256 or _sha("none"),
        )
        signed = SignedEvaluationConformanceObservation(
            observation=observation,
            signature=EvaluationConformanceSignature(
                signer_id="observer-a",
                public_key_sha256=_sha("observer-key"),
                observation_sha256=observation.observation_sha256,
                signature_base64=signature,
            ),
        )
        receipt = AuthenticatedEvaluationConformance(
            conformance_policy_sha256=observation.conformance_policy_sha256,
            plan_sha256=batch.plan_sha256,
            batch_sha256=batch.batch_sha256,
            sample_id=request.sample_id,
            candidate_id=request.route.candidate_id,
            evaluation_request_sha256=request.request_sha256,
            provider_request_sha256=authorization.provider_request_sha256,
            spend_policy_sha256=authorization.spend_policy_sha256,
            ledger_id=authorization.ledger_id,
            ledger_entry_id=authorization.ledger_entry_id,
            artifact_sha256=artifact.artifact_sha256,
            signer_id="observer-a",
            signed_observation=signed,
            authenticated_at=observed_at,
        )
        receipts.append(receipt)
        artifacts.append(artifact)
        successes.append(
            {
                "artifact_sha256": artifact.artifact_sha256,
                "authenticated_at": "2026-09-09T00:00:00+00:00",
                "authenticated_conformance_sha256": (
                    receipt.authenticated_conformance_sha256
                ),
                "authorization_sha256": artifact.authorization_sha256,
                "cost_microusd": artifact.cost_microusd,
                "latency_ms": artifact.latency_ms,
                "ledger_entry_id": authorization.ledger_entry_id,
                "ledger_id": authorization.ledger_id,
                "outcome_sha256": artifact.outcome_sha256,
                "position": position,
                "profile": f"{model}/{effort}",
                "provider_request_id": artifact.provider_request_id,
                "provider_response_sha256": artifact.provider_response_sha256,
                "qualifying": True,
                "receipt_path": f"private/receipt-{offset}.json",
                "sample_id": request.sample_id,
                "signed_observation_sha256": signed.signed_observation_sha256,
            }
        )
    for excluded in range(2):
        item = successes[-1] | {
            "artifact_sha256": _sha(f"excluded-artifact-{excluded}"),
            "authenticated_conformance_sha256": _sha(f"excluded-receipt-{excluded}"),
            "authorization_sha256": _sha(f"excluded-authorization-{excluded}"),
            "ledger_entry_id": _sha(f"excluded-entry-{excluded}"),
            "outcome_sha256": _sha(f"excluded-outcome-{excluded}"),
            "position": f"astra-high-invalidated-{excluded + 1}",
            "provider_request_id": f"excluded_resp_{excluded}",
            "provider_response_sha256": _sha(f"excluded-response-{excluded}"),
            "qualifying": False,
            "receipt_path": f"private/excluded-{excluded}.json",
            "sample_id": _sha(f"excluded-sample-{excluded}"),
            "signed_observation_sha256": _sha(f"excluded-signed-{excluded}"),
        }
        successes.append(item)
    report = {
        "additional_provider_request_authorized": False,
        "all_authenticated_successes_reverified": 20,
        "batch_conversion_authorized": False,
        "batch_sha256": batch.batch_sha256,
        "billing_reconciled": False,
        "calibration_conversion_performed": False,
        "complete_batch_conformance_proven": False,
        "exact_attempt_coverage_verified": True,
        "failure_sources_reverified": True,
        "grading_authorized": False,
        "historical_authenticated_successes_excluded": 2,
        "mode": "openai_live_conformance_gate_report",
        "no_credential_accessed_during_compilation": True,
        "no_provider_request_sent_during_compilation": True,
        "outcome": "pass",
        "plan_sha256": batch.plan_sha256,
        "profile_count": 6,
        "profile_matrix": {
            f"{model}/{effort}": {
                "positions": list(profile_positions),
                "required_consecutive_successes": 3,
                "verified_qualifying_successes": 3,
            }
            for model, effort, profile_positions in PROFILES
        },
        "promotion_authorized": False,
        "provider_authorship_proven": False,
        "quality_claimed": False,
        "required_execution_positions": 23,
        "required_failure_boundaries": 5,
        "required_success_positions": 18,
        "routing_activation_authorized": False,
        "schema_version": 1,
        "scoring_authorized": False,
        "successes": successes,
        "verified_execution_positions": 23,
        "verified_failure_boundaries": 5,
        "verified_success_positions": 18,
    }
    report_bytes = json.dumps(
        report, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    policy = OpenAIConformanceConversionPolicy(
        policy_id="test-conversion-v1",
        plan_sha256=batch.plan_sha256,
        batch_sha256=batch.batch_sha256,
        gate_report_sha256=digest(report_bytes),
        profiles=tuple(
            OpenAIConformanceProfileRequirement(
                model=model, effort=effort, positions=profile_positions
            )
            for model, effort, profile_positions in PROFILES
        ),
    )
    return batch, report_bytes, policy, tuple(receipts), tuple(artifacts)


class OpenAIConformanceConversionTests(TestCase):
    def test_converts_exact_gate_subset_without_issuing_raw_results(self) -> None:
        batch, report, policy, receipts, artifacts = conversion_inputs()
        seed = convert_openai_conformance_to_calibration_seed(
            batch, report, policy, tuple(reversed(receipts)), tuple(reversed(artifacts))
        )
        self.assertEqual(seed.converted_assignments, 18)
        self.assertEqual(seed.execution_batch_assignments, 19)
        self.assertEqual(
            tuple(item.sample_id for item in seed.results),
            tuple(item.sample_id for item in batch.requests[:18]),
        )
        self.assertTrue(seed.conversion_performed)
        self.assertTrue(seed.partial_calibration_input_issued)
        self.assertTrue(seed.exact_qualifying_source_set_verified)
        self.assertFalse(seed.complete_batch_coverage_verified)
        self.assertFalse(seed.live_raw_result_set_issued)
        self.assertFalse(seed.grading_authorized)
        self.assertFalse(seed.scoring_authorized)
        self.assertFalse(seed.promotion_authorized)
        self.assertFalse(seed.routing_activation_authorized)
        with self.assertRaises(ValidationError):
            RawResultSet.model_validate_json(canonical_bytes(seed))

    def test_rejects_tampering_extra_sources_and_forbidden_gate_claims(self) -> None:
        batch, report, policy, receipts, artifacts = conversion_inputs()
        with self.assertRaisesRegex(ValueError, "gate report does not match"):
            convert_openai_conformance_to_calibration_seed(
                batch, report + b"\n", policy, receipts, artifacts
            )
        pretty_report = json.dumps(json.loads(report), sort_keys=True).encode()
        pretty_policy = policy.model_copy(
            update={"gate_report_sha256": digest(pretty_report)}
        )
        with self.assertRaisesRegex(ValueError, "canonical sorted compact"):
            convert_openai_conformance_to_calibration_seed(
                batch, pretty_report, pretty_policy, receipts, artifacts
            )
        with self.assertRaisesRegex(ValueError, "exactly cover"):
            convert_openai_conformance_to_calibration_seed(
                batch, report, policy, receipts[:-1], artifacts
            )
        changed = artifacts[0].model_copy(update={"outcome_sha256": _sha("changed")})
        with self.assertRaisesRegex(ValueError, "source lineage mismatch"):
            convert_openai_conformance_to_calibration_seed(
                batch, report, policy, receipts, (changed, *artifacts[1:])
            )
        parsed = json.loads(report)
        parsed["grading_authorized"] = True
        changed_report = json.dumps(
            parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        changed_policy = policy.model_copy(
            update={"gate_report_sha256": digest(changed_report)}
        )
        with self.assertRaisesRegex(ValueError, "forbidden"):
            convert_openai_conformance_to_calibration_seed(
                batch, changed_report, changed_policy, receipts, artifacts
            )

    def test_cli_requires_consent_and_refuses_credentials(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "seed.json"
            options = [
                "eval-convert-openai-conformance",
                "--batch",
                str(root / "missing-batch.json"),
                "--gate-report",
                str(root / "missing-gate.json"),
                "--conversion-policy",
                str(root / "missing-policy.json"),
                "--authenticated-conformance",
                str(root / "missing-receipt.json"),
                "--artifact",
                str(root / "missing-artifact.json"),
                "--output",
                str(output),
            ]
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(options), 2)
            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}),
                redirect_stderr(io.StringIO()) as stderr,
            ):
                self.assertEqual(main([*options, "--allow-offline-conversion"]), 2)
            self.assertNotIn("secret", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_cli_writes_private_partial_seed(self) -> None:
        batch, report, policy, receipts, artifacts = conversion_inputs()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            batch_path = root / "batch.json"
            report_path = root / "gate.json"
            policy_path = root / "policy.json"
            output = root / "seed.json"
            private_write(batch_path, canonical_bytes(batch))
            private_write(report_path, report)
            private_write(policy_path, canonical_bytes(policy))
            options = [
                "eval-convert-openai-conformance",
                "--batch",
                str(batch_path),
                "--gate-report",
                str(report_path),
                "--conversion-policy",
                str(policy_path),
                "--allow-offline-conversion",
                "--output",
                str(output),
            ]
            for index, (receipt, artifact) in enumerate(
                zip(receipts, artifacts, strict=True)
            ):
                receipt_path = root / f"receipt-{index}.json"
                artifact_path = root / f"artifact-{index}.json"
                private_write(receipt_path, canonical_bytes(receipt))
                private_write(artifact_path, canonical_bytes(artifact))
                options.extend(("--authenticated-conformance", str(receipt_path)))
                options.extend(("--artifact", str(artifact_path)))
            with (
                patch.dict("os.environ", {}, clear=True),
                redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(main(options), 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["converted_assignments"], 18)
            self.assertFalse(event["live_raw_result_set_issued"])
            self.assertFalse(event["provider_request_sent_during_conversion"])
            parsed = OpenAIConformanceCalibrationSeed.model_validate_json(
                output.read_bytes()
            )
            self.assertEqual(
                event["calibration_seed_sha256"], parsed.calibration_seed_sha256
            )
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
