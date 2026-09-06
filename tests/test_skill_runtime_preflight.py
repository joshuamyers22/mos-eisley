"""Skill runtime preparation burns spend authority but never sends a request."""

import io
import json
import sqlite3
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.registry import ModelRegistry, openai_registry
from mos_eisley.evaluation.models import RouteCandidate
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from mos_eisley.run.skill_runtime_preflight import (
    PreparedSkillRuntimeRequest,
    SkillRuntimeAuthorityPolicy,
    SkillRuntimeDecision,
    SkillRuntimeRequest,
    SkillRuntimeSources,
    inspect_skill_runtime_preflight,
    make_skill_runtime_decision,
    prepare_signed_skill_runtime_request,
    sign_skill_runtime_decision,
    trusted_skill_runtime_authority,
    verify_prepared_skill_runtime_request,
)
from mos_eisley.run.skills import prompt_asset_from_skill_archive
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write
from tests import test_skill_health as health_module


class SkillRuntimePreflightTests(TestCase):
    def setUp(self) -> None:
        self.health = health_module.SkillHealthTests()
        self.health.setUp()
        self.addCleanup(self.health.doCleanups)
        self.signed_health_policy = self.health.signed_policy()
        self.signed_health_observation = self.health.signed_observation()
        self.health_eligibility = self.health.issue(
            signed_policy=self.signed_health_policy,
            signed_observation=self.signed_health_observation,
        )
        values = self.health.source._arguments()  # pyright: ignore[reportPrivateUsage]
        self.sources = SkillRuntimeSources(
            dataset=values[0],  # type: ignore[arg-type]
            plan=values[1],  # type: ignore[arg-type]
            calibration=values[2],  # type: ignore[arg-type]
            holdout=values[3],  # type: ignore[arg-type]
            sealed=values[4],  # type: ignore[arg-type]
            holdout_claim=values[5],  # type: ignore[arg-type]
            calibration_report=values[6],  # type: ignore[arg-type]
            holdout_report=values[7],  # type: ignore[arg-type]
            promotion=values[8],  # type: ignore[arg-type]
            promotion_policy=values[9],  # type: ignore[arg-type]
            archive=values[10],  # type: ignore[arg-type]
            release_evidence=values[11],  # type: ignore[arg-type]
            control=values[12],  # type: ignore[arg-type]
            control_policy=values[13],  # type: ignore[arg-type]
            control_anchor=values[14],  # type: ignore[arg-type]
            installed_store=values[15],  # type: ignore[arg-type]
            installation_policy=values[16],  # type: ignore[arg-type]
            default_store=self.health.source.store,
            default_policy=self.health.source.policy,
            signed_health_policy=self.signed_health_policy,
            signed_health_observation=self.signed_health_observation,
            health_authorities=self.health.authorities,
            health_eligibility=self.health_eligibility,
        )
        self.registry: ModelRegistry = openai_registry()
        registry_sha256 = digest(canonical_bytes(self.registry))
        installed = self.sources.installed_store.load(
            self.health_eligibility.archive_sha256,
            self.sources.installation_policy,
        )[1]
        prompt = prompt_asset_from_skill_archive(installed)
        self.route = RouteCandidate(
            backend="api",
            provider="openai",
            model="gpt-6-astra",
            effort="medium",
            client_version="openai-test",
            registry_sha256=registry_sha256,
            prompt=prompt,
        )
        self.routing_preflight = RoutingRuntimePreflight(
            candidate_policy_sha256="1" * 64,
            promotion_receipt_sha256="2" * 64,
            activation_eligibility_sha256="3" * 64,
            control_anchor_policy_sha256="4" * 64,
            anchored_control_entry_sha256="5" * 64,
            checked_at=self.health.issue_at,
            valid_until=self.health_eligibility.valid_until,
            eligible_candidate_ids=(self.route.candidate_id,),
            unavailable_action="fail_closed",
        )
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ledger = SpendLedger.create(self.root / "spend.sqlite", 500)
        self.spend_policy = SpendPolicy(
            model=self.route.model,
            pricing_source="signed synthetic runtime rates",
            valid_from=self.health.issue_at - timedelta(seconds=1),
            valid_until=self.health_eligibility.valid_until,
            input_microusd_per_million=1_000_000,
            output_microusd_per_million=2_000_000,
            max_cost_microusd=200,
            max_input_tokens=100,
            max_output_tokens=20,
        )
        self.request = SkillRuntimeRequest(
            request_id="6" * 64,
            route=self.route,
            user_input="Review the exact change.",
            max_output_tokens=10,
            routing_preflight_sha256=self.routing_preflight.preflight_sha256,
            skill_health_eligibility_sha256=(
                self.health_eligibility.eligibility_sha256
            ),
            spend_policy_sha256=self.spend_policy.policy_sha256,
            spend_ledger_id=self.ledger.policy.ledger_id,
            external_data_transfer_acknowledged=True,
        )
        self.signer = Ed25519PrivateKey.generate()
        self.runtime_policy = SkillRuntimeAuthorityPolicy(
            policy_id="skill-runtime-authorities-v1",
            health_authority_policy_sha256=self.health.authorities.policy_sha256,
            default_store_policy_sha256=(self.health.source.store.policy.policy_sha256),
            model_registry_sha256=registry_sha256,
            spend_ledger_id=self.ledger.policy.ledger_id,
            valid_from=self.health.issue_at,
            valid_until=self.health_eligibility.valid_until,
            max_decision_lifetime_seconds=20,
            authorities=(
                trusted_skill_runtime_authority(
                    "runtime-preparer", self.signer.public_key().public_bytes_raw()
                ),
            ),
        )
        self.issued_at = self.health.issue_at + timedelta(seconds=1)
        self.valid_until = self.health.issue_at + timedelta(seconds=15)

    def decision(self) -> SkillRuntimeDecision:
        return make_skill_runtime_decision(
            self.sources,
            self.routing_preflight,
            self.request,
            self.registry,
            self.spend_policy,
            self.ledger,
            self.runtime_policy,
            self.issued_at,
            self.valid_until,
        )

    def prepare_signed_fixture(self) -> PreparedSkillRuntimeRequest:
        signed = sign_skill_runtime_decision(
            self.decision(), "runtime-preparer", self.signer.private_bytes_raw()
        )
        return prepare_signed_skill_runtime_request(
            self.sources,
            self.routing_preflight,
            self.request,
            self.registry,
            self.spend_policy,
            self.ledger,
            self.runtime_policy,
            signed,
            self.issued_at + timedelta(seconds=1),
        )

    def test_prepares_exact_prompt_route_and_spend_without_dispatch(self) -> None:
        decision = self.decision()
        signed = sign_skill_runtime_decision(
            decision, "runtime-preparer", self.signer.private_bytes_raw()
        )
        prepared = prepare_signed_skill_runtime_request(
            self.sources,
            self.routing_preflight,
            self.request,
            self.registry,
            self.spend_policy,
            self.ledger,
            self.runtime_policy,
            signed,
            self.issued_at + timedelta(seconds=1),
        )

        self.assertEqual(
            prepared.default_pointer_sha256,
            self.health_eligibility.default_pointer_sha256,
        )
        self.assertEqual(prepared.route, self.route)
        self.assertEqual(
            prepared.provider_request.payload["instructions"],
            self.route.prompt.instructions,
        )
        self.assertEqual(
            prepared.provider_request.payload["input"],
            [{"role": "user", "content": self.request.user_input}],
        )
        self.assertEqual(prepared.spend_reservation.input_tokens, 100)
        self.assertEqual(prepared.spend_reservation.reserved_microusd, 120)
        self.assertTrue(prepared.authorization_consumed)
        self.assertTrue(prepared.spend_reserved)
        self.assertTrue(prepared.prompt_bytes_loaded)
        self.assertFalse(prepared.broker_grant_issued)
        self.assertFalse(prepared.provider_dispatch_authorized)
        self.assertFalse(prepared.provider_request_sent)
        self.assertFalse(prepared.activation_authorized)
        self.assertFalse(prepared.configuration_mutation_authorized)
        self.assertFalse(prepared.automatic_rollback_authorized)
        entry = self.ledger.entry_status(prepared.ledger_entry.entry_id)
        assert entry is not None
        self.assertEqual(entry.status, "held")
        self.assertEqual(self.ledger.snapshot().charged_microusd, 120)
        verify_prepared_skill_runtime_request(
            self.sources,
            self.routing_preflight,
            self.request,
            self.registry,
            self.spend_policy,
            self.ledger,
            self.runtime_policy,
            signed,
            prepared,
            self.issued_at + timedelta(seconds=2),
        )
        changed = prepared.model_copy(update={"provider_request_sent": True})
        with self.assertRaisesRegex(ValueError, "request or reservation"):
            verify_prepared_skill_runtime_request(
                self.sources,
                self.routing_preflight,
                self.request,
                self.registry,
                self.spend_policy,
                self.ledger,
                self.runtime_policy,
                signed,
                changed,
                self.issued_at + timedelta(seconds=2),
            )

    def test_replay_is_denied_and_status_never_allows_retry_or_send(self) -> None:
        decision = self.decision()
        signed = sign_skill_runtime_decision(
            decision, "runtime-preparer", self.signer.private_bytes_raw()
        )
        before = inspect_skill_runtime_preflight(
            signed, self.runtime_policy, self.ledger
        )
        self.assertEqual(before.ledger_status, "absent")
        self.assertFalse(before.authorization_consumed)
        prepare_call = cast(Any, prepare_signed_skill_runtime_request)
        prepared = prepare_call(
            self.sources,
            self.routing_preflight,
            self.request,
            self.registry,
            self.spend_policy,
            self.ledger,
            self.runtime_policy,
            signed,
            self.issued_at + timedelta(seconds=1),
        )
        with self.assertRaisesRegex(ValueError, "already consumed"):
            prepare_call(
                self.sources,
                self.routing_preflight,
                self.request,
                self.registry,
                self.spend_policy,
                self.ledger,
                self.runtime_policy,
                signed,
                self.issued_at + timedelta(seconds=2),
            )
        after = inspect_skill_runtime_preflight(
            signed, self.runtime_policy, self.ledger
        )
        self.assertEqual(after.ledger_entry_id, prepared.ledger_entry.entry_id)
        self.assertEqual(after.ledger_status, "held")
        self.assertTrue(after.authorization_consumed)
        self.assertFalse(after.retry_permitted)
        self.assertFalse(after.provider_dispatch_authorized)
        self.assertFalse(after.automatic_budget_release_authorized)

    def test_prompt_route_registry_and_spend_substitution_fail_before_burn(
        self,
    ) -> None:
        changed_prompt = self.route.prompt.model_copy(
            update={"instructions": self.route.prompt.instructions + "\nChanged."}
        )
        changed_route = self.route.model_copy(update={"prompt": changed_prompt})
        changed_preflight = self.routing_preflight.model_copy(
            update={"eligible_candidate_ids": (changed_route.candidate_id,)}
        )
        changed_request = self.request.model_copy(
            update={
                "route": changed_route,
                "routing_preflight_sha256": changed_preflight.preflight_sha256,
            }
        )
        with self.assertRaisesRegex(ValueError, "exact selected prompt"):
            make_skill_runtime_decision(
                self.sources,
                changed_preflight,
                changed_request,
                self.registry,
                self.spend_policy,
                self.ledger,
                self.runtime_policy,
                self.issued_at,
                self.valid_until,
            )
        absent_route = self.routing_preflight.model_copy(
            update={"eligible_candidate_ids": ("a" * 64,)}
        )
        with self.assertRaisesRegex(ValueError, "absent from routing"):
            make_skill_runtime_decision(
                self.sources,
                absent_route,
                self.request.model_copy(
                    update={"routing_preflight_sha256": absent_route.preflight_sha256}
                ),
                self.registry,
                self.spend_policy,
                self.ledger,
                self.runtime_policy,
                self.issued_at,
                self.valid_until,
            )
        wrong_policy = self.spend_policy.model_copy(update={"model": "other-model"})
        wrong_request = self.request.model_copy(
            update={"spend_policy_sha256": wrong_policy.policy_sha256}
        )
        with self.assertRaisesRegex(ValueError, "route, effort, or output"):
            make_skill_runtime_decision(
                self.sources,
                self.routing_preflight,
                wrong_request,
                self.registry,
                wrong_policy,
                self.ledger,
                self.runtime_policy,
                self.issued_at,
                self.valid_until,
            )
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_signature_authority_expiry_and_worst_case_cost_fail_closed(self) -> None:
        decision = self.decision()
        other = Ed25519PrivateKey.generate()
        bad_signature = sign_skill_runtime_decision(
            decision, "runtime-preparer", other.private_bytes_raw()
        )
        with self.assertRaisesRegex(ValueError, "not enrolled"):
            prepare_signed_skill_runtime_request(
                self.sources,
                self.routing_preflight,
                self.request,
                self.registry,
                self.spend_policy,
                self.ledger,
                self.runtime_policy,
                bad_signature,
                self.issued_at + timedelta(seconds=1),
            )
        signed = sign_skill_runtime_decision(
            decision, "runtime-preparer", self.signer.private_bytes_raw()
        )
        with self.assertRaisesRegex(ValueError, "not current"):
            prepare_signed_skill_runtime_request(
                self.sources,
                self.routing_preflight,
                self.request,
                self.registry,
                self.spend_policy,
                self.ledger,
                self.runtime_policy,
                signed,
                decision.valid_until,
            )
        expensive = self.spend_policy.model_copy(update={"max_input_tokens": 181})
        expensive_request = self.request.model_copy(
            update={"spend_policy_sha256": expensive.policy_sha256}
        )
        with self.assertRaisesRegex(ValueError, "worst-case reservation"):
            make_skill_runtime_decision(
                self.sources,
                self.routing_preflight,
                expensive_request,
                self.registry,
                expensive,
                self.ledger,
                self.runtime_policy,
                self.issued_at,
                self.valid_until,
            )
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_transfer_acknowledgement_and_authority_denials_are_structural(
        self,
    ) -> None:
        request = self.request.model_dump(mode="json")
        request.pop("external_data_transfer_acknowledged")
        with self.assertRaises(ValidationError):
            SkillRuntimeRequest.model_validate(request)
        prepared = self.prepare_signed_fixture()
        for field in (
            "broker_grant_issued",
            "provider_dispatch_authorized",
            "provider_request_sent",
            "activation_authorized",
            "configuration_mutation_authorized",
            "automatic_rollback_authorized",
        ):
            value = prepared.model_dump(mode="json")
            value[field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                type(prepared).model_validate(value)

    def test_ledger_failure_is_atomic_and_does_not_consume_authority(self) -> None:
        signed = sign_skill_runtime_decision(
            self.decision(), "runtime-preparer", self.signer.private_bytes_raw()
        )
        with sqlite3.connect(self.ledger.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_runtime BEFORE INSERT ON entries "
                "BEGIN SELECT RAISE(ABORT, 'simulated runtime failure'); END"
            )
            connection.commit()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated"):
            prepare_signed_skill_runtime_request(
                self.sources,
                self.routing_preflight,
                self.request,
                self.registry,
                self.spend_policy,
                self.ledger,
                self.runtime_policy,
                signed,
                self.issued_at + timedelta(seconds=1),
            )
        self.assertEqual(self.ledger.snapshot().entries, 0)
        status = inspect_skill_runtime_preflight(
            signed, self.runtime_policy, self.ledger
        )
        self.assertFalse(status.authorization_consumed)

    def test_cli_derives_prepares_and_inspects_without_dispatch(self) -> None:
        request_path = self.root / "runtime-request.json"
        routing_path = self.root / "routing-preflight.json"
        registry_path = self.root / "registry.json"
        spend_path = self.root / "spend-policy.json"
        runtime_policy_path = self.root / "runtime-authorities.json"
        for path, artifact in (
            (request_path, self.request),
            (routing_path, self.routing_preflight),
            (registry_path, self.registry),
            (spend_path, self.spend_policy),
            (runtime_policy_path, self.runtime_policy),
        ):
            private_write(path, canonical_bytes(artifact))

        def arguments(command: str, output: Path) -> list[str]:
            dummy = str(self.root / "unused.json")
            result = [command]
            for option in (
                "dataset",
                "plan",
                "sealed-comparison",
                "holdout-use-claim",
                "calibration-report",
                "holdout-report",
                "promotion-receipt",
                "promotion-authority-policy",
                "archive",
                "release-evidence",
                "control-authority-policy",
                "authenticated-control",
                "control-anchor",
                "installed-store",
                "installation-authority-policy",
                "default-store",
                "default-authority-policy",
                "signed-health-policy",
                "signed-health-observation",
                "health-authority-policy",
                "health-eligibility",
            ):
                result.extend((f"--{option}", dummy))
            for prefix in ("calibration", "holdout"):
                for option in (
                    "batch",
                    "mapping",
                    "raw-results",
                    "grading-batch",
                    "dual-grading-resolution",
                    "dual-graded-observations",
                    "grading-trust-policy",
                    "resolution-trust-policy",
                ):
                    result.extend((f"--{prefix}-{option}", dummy))
            result.extend(
                (
                    "--routing-preflight",
                    str(routing_path),
                    "--runtime-request",
                    str(request_path),
                    "--model-registry",
                    str(registry_path),
                    "--spend-policy",
                    str(spend_path),
                    "--spend-ledger",
                    str(self.ledger.path),
                    "--runtime-authority-policy",
                    str(runtime_policy_path),
                    "--output",
                    str(output),
                )
            )
            return result

        inputs = (
            self.sources,
            self.routing_preflight,
            self.request,
            self.registry,
            self.spend_policy,
            self.ledger,
            self.runtime_policy,
        )
        decision_path = self.root / "runtime-decision.json"
        derive = arguments("eval-derive-skill-runtime-preflight", decision_path)
        derive.extend(
            (
                "--issued-at",
                self.issued_at.isoformat(),
                "--valid-until",
                self.valid_until.isoformat(),
            )
        )
        with (
            patch("mos_eisley.cli._load_skill_runtime_inputs", return_value=inputs),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(main(derive), 0)
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_runtime.derived",
        )
        decision = SkillRuntimeDecision.model_validate_json(decision_path.read_bytes())
        signed = sign_skill_runtime_decision(
            decision, "runtime-preparer", self.signer.private_bytes_raw()
        )
        signed_path = self.root / "signed-runtime-decision.json"
        private_write(signed_path, canonical_bytes(signed))
        prepared_path = self.root / "prepared-runtime-request.json"
        prepare = arguments("eval-prepare-skill-runtime-request", prepared_path)
        prepare.extend(("--signed-runtime-decision", str(signed_path)))
        with (
            patch("mos_eisley.cli._load_skill_runtime_inputs", return_value=inputs),
            patch("mos_eisley.cli.datetime") as clock,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            clock.now.return_value = self.issued_at + timedelta(seconds=1)
            self.assertEqual(main(prepare), 0)
        event = json.loads(stdout.getvalue())
        self.assertEqual(event["type"], "evaluation.skill_runtime.prepared")
        self.assertFalse(event["provider_dispatch_authorized"])
        self.assertFalse(event["provider_request_sent"])

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-preflight-status",
                        "--signed-runtime-decision",
                        str(signed_path),
                        "--runtime-authority-policy",
                        str(runtime_policy_path),
                        "--spend-ledger",
                        str(self.ledger.path),
                    ]
                ),
                0,
            )
        status = json.loads(stdout.getvalue())
        self.assertEqual(status["ledger_status"], "held")
        self.assertTrue(status["authorization_consumed"])
        self.assertFalse(status["retry_permitted"])
