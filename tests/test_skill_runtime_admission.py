"""Broker admission claims held runtime spend but grants no provider dispatch."""

import io
import json
import sqlite3
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.skill_runtime_admission import (
    SkillRuntimeAdmissionStore,
    inspect_skill_runtime_admission,
    make_skill_runtime_broker_admission,
)
from mos_eisley.run.skill_runtime_preflight import (
    sign_skill_runtime_decision,
)
from mos_eisley.run.spend_ledger import LedgerSettlement
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_preflight as runtime_module


class SkillRuntimeAdmissionTests(TestCase):
    def setUp(self) -> None:
        self.runtime = runtime_module.SkillRuntimePreflightTests()
        self.runtime.setUp()
        self.addCleanup(self.runtime.doCleanups)
        self.signed = sign_skill_runtime_decision(
            self.runtime.decision(),
            "runtime-preparer",
            self.runtime.signer.private_bytes_raw(),
        )
        self.prepared = runtime_module.prepare_signed_skill_runtime_request(
            self.runtime.sources,
            self.runtime.routing_preflight,
            self.runtime.request,
            self.runtime.registry,
            self.runtime.spend_policy,
            self.runtime.ledger,
            self.runtime.runtime_policy,
            self.signed,
            self.runtime.issued_at + timedelta(seconds=1),
        )
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = SkillRuntimeAdmissionStore.create(
            self.root / "admissions.sqlite",
            self.runtime.admission_store_policy,
            self.runtime.routing_sources.control_anchor,
            self.runtime.sources.control_anchor,
            self.runtime.sources.default_store,
            self.runtime.ledger,
        )
        self.admit_at = self.runtime.issued_at + timedelta(seconds=2)

    def admit(self):
        return make_skill_runtime_broker_admission(
            self.runtime.sources,
            self.runtime.routing_preflight,
            self.runtime.request,
            self.runtime.registry,
            self.runtime.spend_policy,
            self.runtime.ledger,
            self.runtime.runtime_policy,
            self.signed,
            self.prepared,
            self.store,
            self.admit_at,
        )

    def test_admission_reverifies_both_lineages_without_second_reservation(
        self,
    ) -> None:
        before = self.runtime.ledger.snapshot()
        admission = self.admit()
        after = self.runtime.ledger.snapshot()

        self.assertEqual(before, after)
        self.assertEqual(after.entries, 1)
        self.assertEqual(admission.ledger_entry_id, self.prepared.ledger_entry.entry_id)
        self.assertTrue(admission.authorization_already_consumed)
        self.assertTrue(admission.existing_reservation_claimed)
        self.assertFalse(admission.second_reservation_created)
        self.assertTrue(admission.one_use_admission_recorded)
        self.assertFalse(admission.broker_grant_issued)
        self.assertFalse(admission.provider_dispatch_authorized)
        self.assertFalse(admission.provider_request_sent)
        self.assertFalse(admission.automatic_retry_authorized)
        self.assertFalse(admission.automatic_budget_release_authorized)
        self.assertEqual(self.store.get(admission.admission_id), admission)
        status = inspect_skill_runtime_admission(
            self.prepared, self.store, self.runtime.ledger
        )
        self.assertEqual((status.phase, status.ledger_status), ("admitted", "held"))
        self.assertFalse(status.retry_permitted)
        self.assertFalse(status.broker_grant_authorized)
        self.assertFalse(status.provider_dispatch_authorized)
        for field in (
            "second_reservation_created",
            "broker_grant_issued",
            "provider_dispatch_authorized",
            "provider_request_sent",
            "automatic_retry_authorized",
            "automatic_budget_release_authorized",
        ):
            changed = admission.model_dump(mode="json")
            changed[field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                type(admission).model_validate(changed)

    def test_replay_is_denied_and_does_not_change_spend(self) -> None:
        admission = self.admit()
        snapshot = self.runtime.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "already recorded"):
            self.admit()
        self.assertEqual(self.runtime.ledger.snapshot(), snapshot)
        self.assertEqual(self.store.get(admission.admission_id), admission)

    def test_different_store_policy_cannot_accept_signed_runtime_request(self) -> None:
        changed_policy = self.runtime.admission_store_policy.model_copy(
            update={"store_id": "8" * 64}
        )
        other = SkillRuntimeAdmissionStore.create(
            self.root / "other-admissions.sqlite",
            changed_policy,
            self.runtime.routing_sources.control_anchor,
            self.runtime.sources.control_anchor,
            self.runtime.sources.default_store,
            self.runtime.ledger,
        )
        with self.assertRaisesRegex(ValueError, "store provenance"):
            make_skill_runtime_broker_admission(
                self.runtime.sources,
                self.runtime.routing_preflight,
                self.runtime.request,
                self.runtime.registry,
                self.runtime.spend_policy,
                self.runtime.ledger,
                self.runtime.runtime_policy,
                self.signed,
                self.prepared,
                other,
                self.admit_at,
            )

    def test_newer_routing_control_rejects_stale_preparation(self) -> None:
        activation = self.runtime.routing_activation
        newer = activation.control.model_copy(
            update={
                "sequence": activation.control.sequence + 1,
                "issued_at": self.admit_at,
            }
        )
        signed_newer = activation.sign_control(newer)
        self.runtime.routing_sources.control_anchor.advance(
            signed_newer,
            activation.authority_policy,
            self.admit_at,
        )
        with self.assertRaisesRegex(ValueError, "latest anchored state"):
            self.admit()
        status = inspect_skill_runtime_admission(
            self.prepared, self.store, self.runtime.ledger
        )
        self.assertEqual(status.phase, "absent")

    def test_nonheld_reservation_rejects_admission(self) -> None:
        self.runtime.ledger.settle(
            LedgerSettlement(
                entry_id=self.prepared.ledger_entry.entry_id,
                reservation_sha256=self.prepared.ledger_entry.reservation_sha256,
                status="uncertain",
                charged_microusd=self.prepared.ledger_entry.reserved_microusd,
            )
        )
        with self.assertRaisesRegex(ValueError, "not current|exact held"):
            self.admit()
        status = inspect_skill_runtime_admission(
            self.prepared, self.store, self.runtime.ledger
        )
        self.assertEqual((status.phase, status.ledger_status), ("absent", "uncertain"))

    def test_store_failure_rolls_back_without_mutating_reservation(self) -> None:
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_admission BEFORE INSERT ON admissions "
                "BEGIN SELECT RAISE(ABORT, 'simulated admission failure'); END"
            )
            connection.commit()
        snapshot = self.runtime.ledger.snapshot()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated"):
            self.admit()
        self.assertEqual(self.runtime.ledger.snapshot(), snapshot)
        status = inspect_skill_runtime_admission(
            self.prepared, self.store, self.runtime.ledger
        )
        self.assertEqual((status.phase, status.ledger_status), ("absent", "held"))

    def test_cli_creates_admits_and_inspects_without_exposing_request(self) -> None:
        admission_policy_path = self.root / "admission-policy.json"
        signed_path = self.root / "signed.json"
        prepared_path = self.root / "prepared.json"
        for path, artifact in (
            (admission_policy_path, self.runtime.admission_store_policy),
            (signed_path, self.signed),
            (prepared_path, self.prepared),
        ):
            private_write(path, canonical_bytes(artifact))
        cli_store_path = self.root / "cli-admissions.sqlite"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-admission-store-create",
                        "--path",
                        str(cli_store_path),
                        "--admission-store-policy",
                        str(admission_policy_path),
                        "--routing-control-anchor",
                        str(self.runtime.routing_sources.control_anchor.path),
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
            "evaluation.skill_runtime.admission_store_created",
        )

        dummy = str(self.root / "unused.json")
        arguments = ["eval-admit-skill-runtime-request"]
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
        output = self.root / "admission.json"
        arguments.extend(
            (
                "--signed-runtime-decision",
                str(signed_path),
                "--prepared-runtime-request",
                str(prepared_path),
                "--admission-store",
                str(cli_store_path),
                "--output",
                str(output),
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
            patch("mos_eisley.cli.datetime") as clock,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            clock.now.return_value = self.admit_at
            self.assertEqual(main(arguments), 0)
        event = json.loads(stdout.getvalue())
        self.assertEqual(event["type"], "evaluation.skill_runtime.broker_admitted")
        self.assertNotIn(self.runtime.request.user_input, stdout.getvalue())
        self.assertFalse(event["provider_dispatch_authorized"])
        self.assertFalse(event["provider_request_sent"])

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-admission-status",
                        "--prepared-runtime-request",
                        str(prepared_path),
                        "--admission-store",
                        str(cli_store_path),
                        "--spend-ledger",
                        str(self.runtime.ledger.path),
                    ]
                ),
                0,
            )
        status = json.loads(stdout.getvalue())
        self.assertEqual(
            (status["phase"], status["ledger_status"]), ("admitted", "held")
        )
        self.assertFalse(status["retry_permitted"])
