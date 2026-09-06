"""Independent one-use runtime dispatch authority remains non-sending."""

import io
import json
import sqlite3
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.skill_runtime_dispatch import (
    SignedSkillRuntimeDispatchDecision,
    SkillRuntimeDispatchAuthorityPolicy,
    SkillRuntimeDispatchClaimStore,
    SkillRuntimeDispatchClaimStorePolicy,
    consume_skill_runtime_dispatch_authority,
    inspect_skill_runtime_dispatch,
    make_skill_runtime_dispatch_decision,
    sign_skill_runtime_dispatch_decision,
    trusted_skill_runtime_dispatch_authority,
)
from mos_eisley.run.spend_ledger import LedgerSettlement
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_admission as admission_module


class SkillRuntimeDispatchTests(TestCase):
    def setUp(self) -> None:
        self.admission_fixture = admission_module.SkillRuntimeAdmissionTests()
        self.admission_fixture.setUp()
        self.addCleanup(self.admission_fixture.doCleanups)
        self.runtime = self.admission_fixture.runtime
        self.admission = self.admission_fixture.admit()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.signer = Ed25519PrivateKey.generate()
        self.claim_policy = SkillRuntimeDispatchClaimStorePolicy(
            store_id="9" * 64,
            admission_store_policy_sha256=(
                self.admission_fixture.store.policy.policy_sha256
            ),
            routing_control_anchor_policy_sha256=(
                self.runtime.sources.routing.control_anchor.policy.policy_sha256
            ),
            skill_control_anchor_policy_sha256=(
                self.runtime.sources.control_anchor.policy.policy_sha256
            ),
            default_store_policy_sha256=(
                self.runtime.sources.default_store.policy.policy_sha256
            ),
            spend_ledger_id=self.runtime.ledger.policy.ledger_id,
        )
        self.policy = SkillRuntimeDispatchAuthorityPolicy(
            policy_id="runtime-dispatch",
            runtime_authority_policy_sha256=self.runtime.runtime_policy.policy_sha256,
            dispatch_claim_store_policy_sha256=self.claim_policy.policy_sha256,
            valid_from=self.runtime.issued_at,
            valid_until=self.admission.valid_until,
            max_decision_lifetime_seconds=30,
            authorities=(
                trusted_skill_runtime_dispatch_authority(
                    "dispatch-authorizer", self.signer.public_key().public_bytes_raw()
                ),
            ),
        )
        self.store = SkillRuntimeDispatchClaimStore.create(
            self.root / "dispatch-claims.sqlite",
            self.claim_policy,
            self.admission_fixture.store,
            self.runtime.sources.routing.control_anchor,
            self.runtime.sources.control_anchor,
            self.runtime.sources.default_store,
            self.runtime.ledger,
        )
        self.issue_at = self.admission_fixture.admit_at + timedelta(seconds=1)
        self.consume_at = self.issue_at + timedelta(seconds=1)

    def decision(self):
        return make_skill_runtime_dispatch_decision(
            self.runtime.sources,
            self.runtime.routing_preflight,
            self.runtime.request,
            self.runtime.registry,
            self.runtime.spend_policy,
            self.runtime.ledger,
            self.runtime.runtime_policy,
            self.admission_fixture.signed,
            self.admission_fixture.prepared,
            self.admission,
            self.admission_fixture.store,
            self.claim_policy,
            self.policy,
            self.issue_at,
            self.issue_at + timedelta(seconds=5),
        )

    def signed_dispatch(self):
        return sign_skill_runtime_dispatch_decision(
            self.decision(),
            "dispatch-authorizer",
            self.signer.private_bytes_raw(),
        )

    def consume(self, signed: SignedSkillRuntimeDispatchDecision):
        return consume_skill_runtime_dispatch_authority(
            self.runtime.sources,
            self.runtime.routing_preflight,
            self.runtime.request,
            self.runtime.registry,
            self.runtime.spend_policy,
            self.runtime.ledger,
            self.runtime.runtime_policy,
            self.admission_fixture.signed,
            self.admission_fixture.prepared,
            self.admission,
            self.admission_fixture.store,
            self.store,
            self.policy,
            signed,
            self.consume_at,
        )

    def cli_runtime_arguments(self, command: str) -> list[str]:
        dummy = str(self.root / "unused.json")
        arguments = [command]
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
            "routing-preflight",
            "runtime-request",
            "model-registry",
            "spend-policy",
            "spend-ledger",
            "runtime-authority-policy",
        ):
            arguments.extend((f"--{option}", dummy))
        for prefix in (
            "calibration",
            "holdout",
            "routing-calibration",
            "routing-holdout",
        ):
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
                arguments.extend((f"--{prefix}-{option}", dummy))
        for option in (
            "routing-dataset",
            "routing-plan",
            "routing-feature-manifest",
            "routing-sealed-study",
            "routing-calibration-report",
            "routing-candidate-policy",
            "routing-promotion-policy",
            "routing-holdout-use-claim",
            "routing-holdout-report",
            "routing-promotion-receipt",
            "routing-promotion-authority-policy",
            "routing-signed-activation-policy",
            "routing-signed-operational-snapshot",
            "routing-signed-control-state",
            "routing-activation-authority-policy",
            "routing-activation-eligibility",
            "routing-control-anchor",
        ):
            arguments.extend((f"--{option}", dummy))
        return arguments

    def test_consumes_exact_authority_once_without_grant_send_or_new_spend(
        self,
    ) -> None:
        signed = self.signed_dispatch()
        before = self.runtime.ledger.snapshot()
        claim = self.consume(signed)

        self.assertEqual(self.runtime.ledger.snapshot(), before)
        self.assertTrue(claim.dispatch_authority_consumed)
        self.assertTrue(claim.request_bound_grant_eligible)
        self.assertFalse(claim.broker_grant_issued)
        self.assertFalse(claim.direct_provider_dispatch_authorized)
        self.assertFalse(claim.provider_request_sent)
        self.assertFalse(claim.automatic_retry_authorized)
        self.assertFalse(claim.automatic_budget_release_authorized)
        self.assertEqual(self.store.get(signed.decision.decision_sha256), claim)
        status = inspect_skill_runtime_dispatch(
            signed, self.policy, self.store, self.runtime.ledger
        )
        self.assertEqual((status.phase, status.ledger_status), ("consumed", "held"))
        self.assertTrue(status.request_bound_grant_eligible)
        self.assertFalse(status.broker_grant_issued)
        self.assertFalse(status.direct_provider_dispatch_authorized)
        self.assertFalse(status.provider_request_sent)
        self.assertFalse(status.retry_permitted)

        for field in (
            "broker_grant_issued",
            "direct_provider_dispatch_authorized",
            "provider_request_sent",
            "automatic_retry_authorized",
            "automatic_budget_release_authorized",
        ):
            changed = claim.model_dump(mode="json")
            changed[field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                type(claim).model_validate(changed)

    def test_replay_fails_closed_without_changing_spend(self) -> None:
        signed = self.signed_dispatch()
        claim = self.consume(signed)
        snapshot = self.runtime.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "already consumed"):
            self.consume(signed)
        self.assertEqual(self.runtime.ledger.snapshot(), snapshot)
        self.assertEqual(self.store.get(signed.decision.decision_sha256), claim)

    def test_signature_cannot_be_rebound_to_another_provider_request(self) -> None:
        signed = self.signed_dispatch()
        changed = signed.decision.model_copy(
            update={"provider_request_sha256": "a" * 64}
        )
        rebound = signed.model_copy(
            update={
                "decision": changed,
                "signature": signed.signature.model_copy(
                    update={"decision_sha256": changed.decision_sha256}
                ),
            }
        )
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            self.consume(rebound)

    def test_runtime_preparer_cannot_also_be_dispatch_authority(self) -> None:
        preparer = self.runtime.signer
        overlapping = self.policy.model_copy(
            update={
                "authorities": (
                    trusted_skill_runtime_dispatch_authority(
                        "runtime-preparer", preparer.public_key().public_bytes_raw()
                    ),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "independent"):
            make_skill_runtime_dispatch_decision(
                self.runtime.sources,
                self.runtime.routing_preflight,
                self.runtime.request,
                self.runtime.registry,
                self.runtime.spend_policy,
                self.runtime.ledger,
                self.runtime.runtime_policy,
                self.admission_fixture.signed,
                self.admission_fixture.prepared,
                self.admission,
                self.admission_fixture.store,
                self.claim_policy,
                overlapping,
                self.issue_at,
                self.issue_at + timedelta(seconds=5),
            )

    def test_stale_routing_control_rejects_without_consuming(self) -> None:
        signed = self.signed_dispatch()
        activation = self.runtime.routing_activation
        newer = activation.control.model_copy(
            update={
                "sequence": activation.control.sequence + 1,
                "issued_at": self.consume_at,
            }
        )
        self.runtime.routing_sources.control_anchor.advance(
            activation.sign_control(newer),
            activation.authority_policy,
            self.consume_at,
        )
        with self.assertRaisesRegex(ValueError, "latest anchored state"):
            self.consume(signed)
        self.assertIsNone(self.store.get(signed.decision.decision_sha256))

    def test_nonheld_spend_rejects_without_consuming(self) -> None:
        signed = self.signed_dispatch()
        entry = self.admission_fixture.prepared.ledger_entry
        self.runtime.ledger.settle(
            LedgerSettlement(
                entry_id=entry.entry_id,
                reservation_sha256=entry.reservation_sha256,
                status="uncertain",
                charged_microusd=entry.reserved_microusd,
            )
        )
        with self.assertRaisesRegex(ValueError, "not current|exact held"):
            self.consume(signed)
        self.assertIsNone(self.store.get(signed.decision.decision_sha256))

    def test_store_failure_leaves_admission_and_spend_unchanged(self) -> None:
        signed = self.signed_dispatch()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_claim BEFORE INSERT ON claims "
                "BEGIN SELECT RAISE(ABORT, 'simulated claim failure'); END"
            )
            connection.commit()
        snapshot = self.runtime.ledger.snapshot()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated"):
            self.consume(signed)
        self.assertEqual(self.runtime.ledger.snapshot(), snapshot)
        self.assertEqual(
            self.admission_fixture.store.get(self.admission.admission_id),
            self.admission,
        )
        self.assertIsNone(self.store.get(signed.decision.decision_sha256))

    def test_cli_derives_consumes_and_inspects_without_exposing_request(self) -> None:
        artifacts = {
            "signed-runtime.json": self.admission_fixture.signed,
            "prepared.json": self.admission_fixture.prepared,
            "admission.json": self.admission,
            "claim-policy.json": self.claim_policy,
            "dispatch-policy.json": self.policy,
        }
        for name, artifact in artifacts.items():
            private_write(self.root / name, canonical_bytes(artifact))
        cli_store = self.root / "cli-dispatch.sqlite"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-dispatch-claim-store-create",
                        "--path",
                        str(cli_store),
                        "--dispatch-claim-store-policy",
                        str(self.root / "claim-policy.json"),
                        "--admission-store",
                        str(self.admission_fixture.store.path),
                        "--routing-control-anchor",
                        str(self.runtime.sources.routing.control_anchor.path),
                        "--skill-control-anchor",
                        str(self.runtime.sources.control_anchor.path),
                        "--default-store",
                        str(self.runtime.sources.default_store.path),
                        "--spend-ledger",
                        str(self.runtime.ledger.path),
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_runtime.dispatch_claim_store_created",
        )

        common_paths = (
            "--signed-runtime-decision",
            str(self.root / "signed-runtime.json"),
            "--prepared-runtime-request",
            str(self.root / "prepared.json"),
            "--admission",
            str(self.root / "admission.json"),
            "--admission-store",
            str(self.admission_fixture.store.path),
            "--dispatch-authority-policy",
            str(self.root / "dispatch-policy.json"),
        )
        decision_path = self.root / "dispatch-decision.json"
        derive = self.cli_runtime_arguments("eval-derive-skill-runtime-dispatch")
        derive.extend(common_paths)
        derive.extend(
            (
                "--dispatch-claim-store-policy",
                str(self.root / "claim-policy.json"),
                "--issued-at",
                self.issue_at.isoformat(),
                "--valid-until",
                (self.issue_at + timedelta(seconds=5)).isoformat(),
                "--output",
                str(decision_path),
            )
        )
        inputs = (
            self.runtime.sources,
            self.runtime.routing_preflight,
            self.runtime.request,
            self.runtime.registry,
            self.runtime.spend_policy,
            self.runtime.ledger,
            self.runtime.runtime_policy,
        )
        with (
            patch("mos_eisley.cli._load_skill_runtime_inputs", return_value=inputs),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(main(derive), 0)
        event = json.loads(stdout.getvalue())
        self.assertEqual(event["type"], "evaluation.skill_runtime.dispatch_derived")
        self.assertFalse(event["direct_provider_dispatch_authorized"])
        self.assertFalse(event["broker_grant_issued"])
        self.assertNotIn(self.runtime.request.user_input, stdout.getvalue())

        decision = self.decision()
        signed_dispatch = sign_skill_runtime_dispatch_decision(
            decision, "dispatch-authorizer", self.signer.private_bytes_raw()
        )
        signed_dispatch_path = self.root / "signed-dispatch.json"
        private_write(signed_dispatch_path, canonical_bytes(signed_dispatch))
        claim_path = self.root / "dispatch-claim.json"
        consume = self.cli_runtime_arguments("eval-consume-skill-runtime-dispatch")
        consume.extend(common_paths)
        consume.extend(
            (
                "--dispatch-claim-store",
                str(cli_store),
                "--signed-dispatch-decision",
                str(signed_dispatch_path),
                "--output",
                str(claim_path),
            )
        )
        with (
            patch("mos_eisley.cli._load_skill_runtime_inputs", return_value=inputs),
            patch("mos_eisley.cli.datetime") as clock,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            clock.now.return_value = self.consume_at
            self.assertEqual(main(consume), 0)
        event = json.loads(stdout.getvalue())
        self.assertEqual(
            event["type"],
            "evaluation.skill_runtime.dispatch_authority_consumed",
        )
        self.assertTrue(event["request_bound_grant_eligible"])
        self.assertFalse(event["provider_request_sent"])
        self.assertNotIn(self.runtime.request.user_input, stdout.getvalue())

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-dispatch-status",
                        "--signed-dispatch-decision",
                        str(signed_dispatch_path),
                        "--dispatch-authority-policy",
                        str(self.root / "dispatch-policy.json"),
                        "--dispatch-claim-store",
                        str(cli_store),
                        "--spend-ledger",
                        str(self.runtime.ledger.path),
                    ]
                ),
                0,
            )
        status = json.loads(stdout.getvalue())
        self.assertEqual(
            (status["phase"], status["ledger_status"]), ("consumed", "held")
        )
        self.assertFalse(status["provider_request_sent"])
