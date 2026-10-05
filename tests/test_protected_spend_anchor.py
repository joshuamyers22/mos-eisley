"""Remote-boundary fixtures, never a claim that a service has been deployed."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
import asyncio
import base64
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from protected_anchor_fixture import FixtureAnchorService, fixture_anchor

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_provenance import G4ProvenanceTrustPolicy, provenance_signer
from mos_eisley.run.protected_spend_anchor import (
    RECEIPT_DOMAIN,
    AnchorRequest,
    ProtectedAnchorGuard,
    SignedAnchorReceipt,
    SignedProtectedAnchorBinding,
    sign_anchor_binding,
    verify_protected_anchor_audit,
)
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger


class ProtectedAnchorTests(TestCase):
    def setUp(self) -> None:
        from datetime import UTC, datetime, timedelta

        self.owner = Ed25519PrivateKey.generate()
        self.remote = FixtureAnchorService(self.owner)
        human = provenance_signer("creator", self.owner.public_key())
        now = datetime.now(UTC)
        self.policy = G4ProvenanceTrustPolicy(
            schema_version=2,
            policy_id="protected-anchor-test",
            creators=(human,),
            reviewers=(human,),
            vcs_brokers=(human,),
            children=(
                provenance_signer("child", Ed25519PrivateKey.generate().public_key()),
            ),
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=1),
            operator_mode="single_operator",
        )

    def entry(self, name: str = "grant", amount: int = 400) -> LedgerEntry:
        return LedgerEntry(
            entry_id=digest(name.encode()),
            reservation_sha256=digest(b"reservation"),
            reserved_microusd=amount,
        )

    def test_copied_restored_ledger_and_new_guard_cannot_redeem_grant(self) -> None:
        with TemporaryDirectory() as name:
            root = Path(name)
            ledger = SpendLedger.create(root / "original.sqlite", 5000)
            before = ledger.path.read_bytes()
            entry = self.entry()
            guard = fixture_anchor(self.owner, ledger, entry.entry_id, self.remote)
            guard.claim(entry.entry_id, self.policy, ledger.policy, entry)
            ledger.reserve(entry)
            for path in (root / "copy.sqlite", ledger.path):
                path.write_bytes(before)
                restored = SpendLedger(path)
                restarted = ProtectedAnchorGuard(guard.binding, self.remote)
                with self.assertRaisesRegex(ValueError, "already spent"):
                    restarted.claim(entry.entry_id, self.policy, restored.policy, entry)
                self.assertEqual(restored.snapshot().entries, 0)
            self.assertEqual(self.remote.held, 400)

    def test_revocation_and_epoch_reset_block_remaining_stages(self) -> None:
        for reset in (False, True):
            with self.subTest(epoch_reset=reset), TemporaryDirectory() as name:
                ledger = SpendLedger.create(Path(name) / "ledger.sqlite", 5000)
                remote = FixtureAnchorService(self.owner)
                entry = self.entry()
                guard = fixture_anchor(self.owner, ledger, entry.entry_id, remote)
                guard.claim(entry.entry_id, self.policy, ledger.policy, entry)
                if reset:
                    remote.epoch += 1
                else:
                    remote.revoked = True
                with self.assertRaisesRegex(ValueError, "epoch, cap or revocation"):
                    guard.admit_stage("count")
                self.assertEqual(remote.held, 400)
                with self.assertRaisesRegex(ValueError, "already spent"):
                    guard.admit_stage("send")

    def test_cross_owner_and_changed_cap_or_grant_are_denied(self) -> None:
        with TemporaryDirectory() as name:
            ledger = SpendLedger.create(Path(name) / "ledger.sqlite", 5000)
            entry = self.entry()
            original = fixture_anchor(self.owner, ledger, entry.entry_id, self.remote)
            for update in (
                {"owner_id": "other-owner"},
                {"scope_ceiling_microusd": 10000},
                {"epoch": 2},
                {"grant_sha256": digest(b"other grant")},
            ):
                guard = ProtectedAnchorGuard(
                    sign_anchor_binding(
                        original.binding.binding.model_copy(update=update), self.owner
                    ),
                    self.remote,
                )
                with self.subTest(update=update), self.assertRaises(ValueError):
                    guard.claim(entry.entry_id, self.policy, ledger.policy, entry)
            self.assertEqual(self.remote.held, 0)

    def test_concurrent_claims_share_one_remote_aggregate_cap(self) -> None:
        with TemporaryDirectory() as name:
            ledger = SpendLedger.create(Path(name) / "ledger.sqlite", 5000)
            remote = FixtureAnchorService(self.owner, cap=700)

            def claim(index: int) -> bool:
                entry = self.entry(str(index))
                guard = fixture_anchor(self.owner, ledger, entry.entry_id, remote)
                try:
                    guard.claim(entry.entry_id, self.policy, ledger.policy, entry)
                except ValueError:
                    return False
                return True

            with ThreadPoolExecutor(max_workers=4) as pool:
                admitted = list(pool.map(claim, range(10)))
            self.assertEqual(sum(admitted), 1)
            self.assertEqual(remote.held, 400)

    def test_unavailable_or_substituted_response_never_falls_back_or_retries(
        self,
    ) -> None:
        with TemporaryDirectory() as name:
            ledger = SpendLedger.create(Path(name) / "ledger.sqlite", 5000)
            entry = self.entry()
            for corrupt in (False, True):
                remote = FixtureAnchorService(self.owner)
                guard = fixture_anchor(self.owner, ledger, entry.entry_id, remote)
                original = remote.admit

                def admit(
                    binding: SignedProtectedAnchorBinding,
                    request: AnchorRequest,
                    corrupt: bool = corrupt,
                    original: Callable[
                        [SignedProtectedAnchorBinding, AnchorRequest],
                        SignedAnchorReceipt,
                    ] = original,
                    remote: FixtureAnchorService = remote,
                    timeout_seconds: float = 10.0,
                ) -> SignedAnchorReceipt:
                    if not corrupt:
                        raise TimeoutError("synthetic remote outage")
                    response = original(binding, request)
                    receipt = response.receipt.model_copy(
                        update={"request_sha256": digest(b"copied response nonce")}
                    )
                    return response.model_copy(
                        update={
                            "receipt": receipt,
                            "signature_base64": base64.b64encode(
                                remote.key.sign(
                                    RECEIPT_DOMAIN + canonical_bytes(receipt)
                                )
                            ).decode(),
                        }
                    )

                with patch.object(remote, "admit", side_effect=admit) as callback:
                    with self.assertRaises((ValueError, TimeoutError)):
                        guard.claim(entry.entry_id, self.policy, ledger.policy, entry)
                    with self.assertRaisesRegex(ValueError, "already spent"):
                        guard.claim(entry.entry_id, self.policy, ledger.policy, entry)
                    self.assertEqual(callback.call_count, 1)
                self.assertEqual(ledger.snapshot().entries, 0)

    def test_remote_revocation_after_count_denies_wrapped_generation(self) -> None:
        from test_openai_spend import FakeTransport

        with TemporaryDirectory() as name:
            root = Path(name)
            ledger = SpendLedger.create(root / "ledger.sqlite", 5000)
            entry = self.entry()
            guard = fixture_anchor(self.owner, ledger, entry.entry_id, self.remote)
            guard.claim(entry.entry_id, self.policy, ledger.policy, entry)
            transport = FakeTransport(root)
            wrapped = guard.wrap_transport(transport, root)
            asyncio.run(wrapped.count_input_tokens({}))
            self.remote.revoked = True
            with self.assertRaisesRegex(ValueError, "revocation"):
                asyncio.run(wrapped.create_response({}))
            self.assertEqual(len(transport.counts), 1)
            self.assertEqual(transport.calls, [])
            self.assertEqual(self.remote.held, 400)

    def test_provider_deadline_cannot_be_extended_by_longer_anchor_binding(
        self,
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from test_openai_spend import FakeTransport

        with TemporaryDirectory() as name:
            root = Path(name)
            ledger = SpendLedger.create(root / "ledger.sqlite", 5000)
            entry = self.entry()
            guard = fixture_anchor(self.owner, ledger, entry.entry_id, self.remote)
            deadline = datetime.now(UTC) + timedelta(seconds=60)
            guard.claim(
                entry.entry_id, self.policy, ledger.policy, entry, deadline=deadline
            )
            transport = FakeTransport(root)
            wrapped = guard.wrap_transport(transport, root)
            with patch("mos_eisley.run.protected_spend_anchor.datetime") as clock:
                clock.now.return_value = deadline
                with self.assertRaisesRegex(ValueError, "expired"):
                    asyncio.run(wrapped.count_input_tokens({}))
            self.assertEqual(self.remote.sequence, 1)
            self.assertEqual(transport.counts, [])

    def test_retained_remote_audit_rejects_changed_stage(self) -> None:
        from test_openai_spend import FakeTransport

        with TemporaryDirectory() as name:
            root = Path(name)
            ledger = SpendLedger.create(root / "ledger.sqlite", 5000)
            entry = self.entry()
            guard = fixture_anchor(self.owner, ledger, entry.entry_id, self.remote)
            guard.claim(entry.entry_id, self.policy, ledger.policy, entry)
            transport = FakeTransport(root)
            wrapped = guard.wrap_transport(transport, root)
            asyncio.run(wrapped.count_input_tokens({}))
            with patch.object(transport, "create_response", return_value={}):
                asyncio.run(wrapped.create_response({}))
            audit = verify_protected_anchor_audit(
                root, self.policy, entry.entry_id, ledger.policy, entry
            )
            self.assertEqual(len(audit), 64)
            path = root / "protected-anchor-send.json"
            original = path.read_bytes()
            path.write_bytes(original.replace(b'"stage":"send"', b'"stage":"count"'))
            with self.assertRaisesRegex(ValueError, "stale or substituted"):
                verify_protected_anchor_audit(
                    root, self.policy, entry.entry_id, ledger.policy, entry
                )

    def test_missing_anchor_blocks_both_live_brokers_before_count_or_spend(
        self,
    ) -> None:
        from test_reviewer_coding_broker import ProductionCodingChildBrokerTests
        from test_reviewer_initial_coding_broker import InitialChildBrokerTests

        with TemporaryDirectory() as name:
            coding = ProductionCodingChildBrokerTests()._setup(Path(name))
            broker, offer = coding[:2]
            broker._protected_anchor = None
            with self.assertRaisesRegex(ValueError, "protected remote"):
                asyncio.run(broker.generate(offer))
            self.assertEqual(broker._ledger.snapshot().entries, 0)
            self.assertEqual(coding[6].counts, 0)
        with TemporaryDirectory() as name:
            initial = InitialChildBrokerTests()._setup(Path(name))
            initial_broker, initial_offer = initial[:2]
            initial_broker._protected_anchor = None
            with self.assertRaisesRegex(ValueError, "protected remote"):
                asyncio.run(initial_broker.generate(initial_offer))
            self.assertEqual(initial_broker._ledger.snapshot().entries, 0)
            self.assertEqual(initial[5].counts, 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
