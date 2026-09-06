"""Runtime grant issuance creates one ephemeral bearer and never sends."""

import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.skill_runtime_grant import (
    SkillRuntimeBrokerCapability,
    SkillRuntimeBrokerGrantStore,
    inspect_skill_runtime_broker_grant,
    issue_skill_runtime_broker_capability,
)
from mos_eisley.run.spend_ledger import LedgerSettlement
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_dispatch as dispatch_module


class SkillRuntimeBrokerGrantTests(TestCase):
    def setUp(self) -> None:
        self.dispatch = dispatch_module.SkillRuntimeDispatchTests()
        self.dispatch.setUp()
        self.addCleanup(self.dispatch.doCleanups)
        self.signed_dispatch = self.dispatch.signed_dispatch()
        self.dispatch_claim = self.dispatch.consume(self.signed_dispatch)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = SkillRuntimeBrokerGrantStore.create(
            self.root / "broker-grants.sqlite",
            self.dispatch.grant_policy,
            self.dispatch.store,
            self.dispatch.admission_fixture.store,
            self.dispatch.runtime.sources.routing.control_anchor,
            self.dispatch.runtime.sources.control_anchor,
            self.dispatch.runtime.sources.default_store,
            self.dispatch.runtime.ledger,
        )
        self.issue_at = self.dispatch.consume_at + timedelta(seconds=1)

    def issue(self, store: SkillRuntimeBrokerGrantStore | None = None):
        runtime = self.dispatch.runtime
        admission_fixture = self.dispatch.admission_fixture
        return issue_skill_runtime_broker_capability(
            runtime.sources,
            runtime.routing_preflight,
            runtime.request,
            runtime.registry,
            runtime.spend_policy,
            runtime.ledger,
            runtime.runtime_policy,
            admission_fixture.signed,
            admission_fixture.prepared,
            self.dispatch.admission,
            admission_fixture.store,
            self.dispatch.store,
            self.dispatch.policy,
            self.signed_dispatch,
            self.dispatch_claim,
            store or self.store,
            self.issue_at,
            15,
        )

    def test_issues_one_memory_only_bearer_without_send_or_new_spend(self) -> None:
        before = self.dispatch.runtime.ledger.snapshot()
        capability = self.issue()
        issuance = capability.issuance
        claim = capability.claim()

        self.assertEqual(self.dispatch.runtime.ledger.snapshot(), before)
        self.assertTrue(issuance.broker_grant_issued)
        self.assertTrue(issuance.request_bound_broker_redemption_authorized)
        self.assertFalse(issuance.direct_provider_dispatch_authorized)
        self.assertFalse(issuance.provider_request_sent)
        self.assertFalse(issuance.automatic_retry_authorized)
        self.assertFalse(issuance.automatic_budget_release_authorized)
        self.assertEqual(claim.request_sha256, issuance.broker_request_sha256)
        self.assertEqual(claim.authorization_sha256, issuance.issuance_sha256)
        self.assertNotIn(claim.capability, repr(capability))
        self.assertNotIn(claim.capability.encode(), self.store.path.read_bytes())
        with self.assertRaisesRegex(ValueError, "unavailable"):
            capability.claim()
        self.assertEqual(capability.redeem(canonical_bytes(claim)), issuance)
        with self.assertRaisesRegex(ValueError, "rejected"):
            capability.redeem(canonical_bytes(claim))
        self.assertEqual(
            self.store.get(self.signed_dispatch.decision.decision_sha256), issuance
        )
        status = inspect_skill_runtime_broker_grant(
            self.signed_dispatch,
            self.dispatch.policy,
            self.store,
            self.dispatch.runtime.ledger,
        )
        self.assertEqual((status.phase, status.ledger_status), ("issued", "held"))
        self.assertTrue(status.broker_grant_issued)
        self.assertFalse(status.direct_provider_dispatch_authorized)
        self.assertFalse(status.provider_request_sent)
        self.assertFalse(status.retry_permitted)

        for field in (
            "direct_provider_dispatch_authorized",
            "provider_request_sent",
            "automatic_retry_authorized",
            "automatic_budget_release_authorized",
        ):
            changed = issuance.model_dump(mode="json")
            changed[field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                type(issuance).model_validate(changed)

    def test_replay_cannot_issue_another_bearer(self) -> None:
        first = self.issue().issuance
        snapshot = self.dispatch.runtime.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "already issued"):
            self.issue()
        self.assertEqual(self.dispatch.runtime.ledger.snapshot(), snapshot)
        self.assertEqual(
            self.store.get(self.signed_dispatch.decision.decision_sha256), first
        )

    def test_expired_capability_cannot_be_delivered(self) -> None:
        with patch("mos_eisley.run.skill_runtime_grant.time.monotonic", return_value=0):
            capability = self.issue()
        with (
            patch(
                "mos_eisley.run.skill_runtime_grant.time.monotonic",
                return_value=31,
            ),
            self.assertRaisesRegex(ValueError, "unavailable"),
        ):
            capability.claim()

    def test_expiry_during_commit_records_issuance_but_returns_no_bearer(self) -> None:
        with (
            patch(
                "mos_eisley.run.skill_runtime_grant.time.monotonic",
                side_effect=(0, 31),
            ),
            self.assertRaisesRegex(ValueError, "expired during durable issuance"),
        ):
            self.issue()
        issuance = self.store.get(self.signed_dispatch.decision.decision_sha256)
        self.assertIsNotNone(issuance)
        with self.assertRaisesRegex(ValueError, "already issued"):
            self.issue()

    def test_callers_cannot_reconstruct_a_capability_object(self) -> None:
        capability = self.issue()
        claim = capability.claim()
        with self.assertRaisesRegex(ValueError, "constructed by its issuer"):
            SkillRuntimeBrokerCapability(
                capability.issuance,
                claim.capability,
                1,
                factory=object(),
            )

    def test_store_rejects_mismatched_issuance_before_insert(self) -> None:
        issuance = self.issue().issuance.model_copy(
            update={"provider_request_sha256": "0" * 64}
        )
        other = SkillRuntimeBrokerGrantStore.create(
            self.root / "other-grants.sqlite",
            self.dispatch.grant_policy,
            self.dispatch.store,
            self.dispatch.admission_fixture.store,
            self.dispatch.runtime.sources.routing.control_anchor,
            self.dispatch.runtime.sources.control_anchor,
            self.dispatch.runtime.sources.default_store,
            self.dispatch.runtime.ledger,
        )
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            other.issue(issuance, self.dispatch_claim, self.signed_dispatch)
        self.assertIsNone(other.get(self.signed_dispatch.decision.decision_sha256))

    def test_malformed_or_substituted_claim_does_not_consume_bearer(self) -> None:
        capability = self.issue()
        claim = capability.claim()
        for wire in (
            b"not json",
            b"x" * 1025,
            canonical_bytes(claim.model_copy(update={"request_sha256": "0" * 64})),
            canonical_bytes(
                claim.model_copy(update={"authorization_sha256": "0" * 64})
            ),
        ):
            with self.assertRaisesRegex(ValueError, "rejected"):
                capability.redeem(wire)
        self.assertEqual(capability.redeem(canonical_bytes(claim)), capability.issuance)

    def test_concurrent_redemption_succeeds_exactly_once(self) -> None:
        capability = self.issue()
        wire = canonical_bytes(capability.claim())
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(_redeem_result, capability, wire),
                executor.submit(_redeem_result, capability, wire),
            )
            results = tuple(future.result() for future in futures)
        self.assertEqual(results.count("redeemed"), 1)
        self.assertEqual(results.count("rejected"), 1)

    def test_nonheld_spend_rejects_before_grant_issuance(self) -> None:
        entry = self.dispatch.admission_fixture.prepared.ledger_entry
        self.dispatch.runtime.ledger.settle(
            LedgerSettlement(
                entry_id=entry.entry_id,
                reservation_sha256=entry.reservation_sha256,
                status="uncertain",
                charged_microusd=entry.reserved_microusd,
            )
        )
        with self.assertRaisesRegex(ValueError, "not current|exact held"):
            self.issue()
        self.assertIsNone(self.store.get(self.signed_dispatch.decision.decision_sha256))

    def test_store_failure_returns_no_bearer_and_preserves_prior_state(self) -> None:
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_grant BEFORE INSERT ON grants "
                "BEGIN SELECT RAISE(ABORT, 'simulated grant failure'); END"
            )
            connection.commit()
        snapshot = self.dispatch.runtime.ledger.snapshot()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated"):
            self.issue()
        self.assertEqual(self.dispatch.runtime.ledger.snapshot(), snapshot)
        self.assertEqual(
            self.dispatch.store.get(self.signed_dispatch.decision.decision_sha256),
            self.dispatch_claim,
        )
        self.assertIsNone(self.store.get(self.signed_dispatch.decision.decision_sha256))

    def test_cli_creates_and_inspects_store_without_bearer_recovery(self) -> None:
        policy_path = self.root / "grant-policy.json"
        signed_path = self.root / "signed-dispatch.json"
        dispatch_policy_path = self.root / "dispatch-policy.json"
        for path, artifact in (
            (policy_path, self.dispatch.grant_policy),
            (signed_path, self.signed_dispatch),
            (dispatch_policy_path, self.dispatch.policy),
        ):
            private_write(path, canonical_bytes(artifact))
        cli_store_path = self.root / "cli-grants.sqlite"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-broker-grant-store-create",
                        "--path",
                        str(cli_store_path),
                        "--broker-grant-store-policy",
                        str(policy_path),
                        "--dispatch-claim-store",
                        str(self.dispatch.store.path),
                        "--admission-store",
                        str(self.dispatch.admission_fixture.store.path),
                        "--routing-control-anchor",
                        str(self.dispatch.runtime.sources.routing.control_anchor.path),
                        "--skill-control-anchor",
                        str(self.dispatch.runtime.sources.control_anchor.path),
                        "--default-store",
                        str(self.dispatch.runtime.sources.default_store.path),
                        "--spend-ledger",
                        str(self.dispatch.runtime.ledger.path),
                    ]
                ),
                0,
            )
        event = json.loads(stdout.getvalue())
        self.assertEqual(
            event["type"], "evaluation.skill_runtime.broker_grant_store_created"
        )
        self.assertFalse(event["provider_request_sent"])

        cli_store = SkillRuntimeBrokerGrantStore(cli_store_path)
        capability = self.issue(cli_store)
        secret = capability.claim().capability
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-broker-grant-status",
                        "--signed-dispatch-decision",
                        str(signed_path),
                        "--dispatch-authority-policy",
                        str(dispatch_policy_path),
                        "--broker-grant-store",
                        str(cli_store_path),
                        "--spend-ledger",
                        str(self.dispatch.runtime.ledger.path),
                    ]
                ),
                0,
            )
        status = json.loads(stdout.getvalue())
        self.assertEqual((status["phase"], status["ledger_status"]), ("issued", "held"))
        self.assertTrue(status["broker_grant_issued"])
        self.assertFalse(status["provider_request_sent"])
        self.assertNotIn(secret, stdout.getvalue())


def _redeem_result(capability: SkillRuntimeBrokerCapability, wire: bytes) -> str:
    try:
        capability.redeem(wire)
    except ValueError:
        return "rejected"
    return "redeemed"
