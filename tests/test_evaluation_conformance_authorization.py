"""Signed conformance authority is exact, independent, short-lived, and no-send."""

import base64
import io
import json
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.evaluation_conformance import (
    prepare_evaluation_conformance_policy,
    trusted_evaluation_conformance_observer,
)
from mos_eisley.run.evaluation_conformance_authorization import (
    EvaluationConformanceAuthorityPolicy,
    EvaluationConformanceAuthorization,
    SignedEvaluationConformanceAuthorization,
    make_evaluation_conformance_authorization,
    sign_evaluation_conformance_authorization,
    trusted_evaluation_conformance_authority,
    verify_evaluation_conformance_authorization,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write
from tests.test_openai_conformance import conformance_inputs


class EvaluationConformanceAuthorizationTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.batch, self.spend_policy = conformance_inputs()
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 20_000)
        self.now = datetime.now(UTC)
        observer_key = Ed25519PrivateKey.generate()
        observer = trusted_evaluation_conformance_observer(
            "observer-a", observer_key.public_key().public_bytes_raw()
        )
        self.conformance_policy = prepare_evaluation_conformance_policy(
            self.batch,
            self.batch.requests[0].sample_id,
            self.spend_policy,
            self.ledger,
            self.root / "audit",
            "openai-probe-1",
            self.now - timedelta(minutes=5),
            self.now + timedelta(minutes=30),
            120,
            (observer,),
            ("2.54.0",),
        )
        self.authority_key = Ed25519PrivateKey.generate()
        self.authority_policy = EvaluationConformanceAuthorityPolicy(
            policy_id="openai-conformance-authority",
            valid_from=self.now - timedelta(minutes=5),
            valid_until=self.now + timedelta(minutes=30),
            max_authorization_lifetime_seconds=900,
            authorities=(
                trusted_evaluation_conformance_authority(
                    "transfer-authorizer",
                    self.authority_key.public_key().public_bytes_raw(),
                ),
            ),
        )

    def authorization(self) -> EvaluationConformanceAuthorization:
        return make_evaluation_conformance_authorization(
            self.conformance_policy,
            self.spend_policy,
            self.authority_policy,
            self.now - timedelta(minutes=1),
            self.now + timedelta(minutes=10),
        )

    def signed(self) -> SignedEvaluationConformanceAuthorization:
        return sign_evaluation_conformance_authorization(
            self.authorization(),
            "transfer-authorizer",
            self.authority_key.private_bytes_raw(),
        )

    def test_authenticates_exact_transfer_and_spend_scope(self) -> None:
        authorization = verify_evaluation_conformance_authorization(
            self.signed(),
            self.authority_policy,
            self.conformance_policy,
            self.spend_policy,
            self.now,
        )
        self.assertEqual(
            authorization.conformance_policy_sha256,
            self.conformance_policy.policy_sha256,
        )
        self.assertEqual(
            authorization.max_cost_microusd,
            self.spend_policy.max_cost_microusd,
        )
        self.assertTrue(authorization.blinded_data_transfer_authorized)
        self.assertTrue(authorization.credential_access_authorized)
        self.assertTrue(authorization.spend_authorized)
        self.assertFalse(authorization.unblinded_data_transfer_authorized)
        self.assertFalse(authorization.automatic_retry_authorized)
        self.assertFalse(authorization.scoring_authorized)
        self.assertFalse(authorization.promotion_authorized)

    def test_tamper_substitution_and_expiry_fail_closed(self) -> None:
        signed = self.signed()
        tampered = signed.model_copy(
            update={
                "authorization": signed.authorization.model_copy(
                    update={"max_cost_microusd": 1}
                )
            }
        )
        with self.assertRaises(ValueError):
            verify_evaluation_conformance_authorization(
                tampered,
                self.authority_policy,
                self.conformance_policy,
                self.spend_policy,
                self.now,
            )

        changed_spend = self.spend_policy.model_copy(
            update={"max_cost_microusd": self.spend_policy.max_cost_microusd - 1}
        )
        with self.assertRaisesRegex(ValueError, "spending provenance"):
            verify_evaluation_conformance_authorization(
                signed,
                self.authority_policy,
                self.conformance_policy,
                changed_spend,
                self.now,
            )

        with self.assertRaisesRegex(ValueError, "current policy"):
            verify_evaluation_conformance_authorization(
                signed,
                self.authority_policy,
                self.conformance_policy,
                self.spend_policy,
                signed.authorization.valid_until + timedelta(seconds=1),
            )

    def test_authority_must_be_independent_and_window_is_bounded(self) -> None:
        observer = self.conformance_policy.observers[0]
        overlapping = EvaluationConformanceAuthorityPolicy(
            policy_id="overlapping-authority",
            valid_from=self.now - timedelta(minutes=5),
            valid_until=self.now + timedelta(minutes=30),
            max_authorization_lifetime_seconds=900,
            authorities=(
                trusted_evaluation_conformance_authority(
                    observer.observer_id,
                    base64.b64decode(observer.public_key_base64),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "independent"):
            make_evaluation_conformance_authorization(
                self.conformance_policy,
                self.spend_policy,
                overlapping,
                self.now,
                self.now + timedelta(minutes=1),
            )

        with self.assertRaisesRegex(ValueError, "window exceeds"):
            make_evaluation_conformance_authorization(
                self.conformance_policy,
                self.spend_policy,
                self.authority_policy,
                self.now,
                self.now + timedelta(seconds=901),
            )

    def test_derive_cli_is_unsigned_and_never_accesses_credentials(self) -> None:
        conformance_path = self.root / "conformance-policy.json"
        spend_path = self.root / "spend-policy.json"
        authority_path = self.root / "authority-policy.json"
        output_path = self.root / "authorization.json"
        private_write(conformance_path, canonical_bytes(self.conformance_policy))
        private_write(spend_path, canonical_bytes(self.spend_policy))
        private_write(authority_path, canonical_bytes(self.authority_policy))
        with (
            patch("mos_eisley.cli._openai_api_key") as credential,
            patch("mos_eisley.cli.run_isolated_broker") as dispatch,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(
                main(
                    [
                        "eval-derive-brokered-conformance-authorization",
                        "--conformance-policy",
                        str(conformance_path),
                        "--spend-policy",
                        str(spend_path),
                        "--authority-policy",
                        str(authority_path),
                        "--issued-at",
                        (self.now - timedelta(minutes=1)).isoformat(),
                        "--valid-until",
                        (self.now + timedelta(minutes=10)).isoformat(),
                        "--output",
                        str(output_path),
                    ]
                ),
                0,
            )
        credential.assert_not_called()
        dispatch.assert_not_called()
        event = json.loads(stdout.getvalue())
        self.assertFalse(event["authenticated"])
        self.assertFalse(event["credential_accessed"])
        self.assertFalse(event["provider_request_sent"])
        self.assertFalse(event["spend_reserved"])
        authorization = EvaluationConformanceAuthorization.model_validate_json(
            output_path.read_bytes()
        )
        self.assertEqual(
            event["authorization_sha256"], authorization.authorization_sha256
        )
