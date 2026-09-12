import fcntl
import json
import os
import unittest
from typing import cast

import test_project_guidance_role as role_fixture

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_role_admission import (
    RoleContextAdmissionStore,
    RoleContextSelection,
)
from mos_eisley.project_guidance_role_store import role_snapshot_name


class RoleAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = role_fixture.RoleContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.receipt = self.fixture.freeze()
        self.snapshot = self.fixture.snapshot(self.receipt)
        self.store = RoleContextAdmissionStore(self.fixture.storage)
        self.selection = RoleContextSelection(
            snapshot_sha256=self.snapshot.sha256,
            context_sha256=cast(str, self.receipt["context_sha256"]),
            role=self.snapshot.context.role,
            scope=self.snapshot.context.scope,
        )
        self.policy_sha = digest(self.fixture.policy_path.read_bytes())

    def check(self, selection: RoleContextSelection | None = None) -> dict[str, object]:
        return self.store.check_context(
            self.fixture.workspace,
            selection or self.selection,
            self.fixture.policy_path,
            self.policy_sha,
        )

    def reassess(self) -> None:
        path = self.fixture.fixture.assessment
        data = json.loads(path.read_text())
        data["review_rationale"] += " Revisited."
        path.write_text(json.dumps(data))
        self.fixture.fixture.assess()

    def test_check_is_current_read_only_and_has_no_private_payload(self) -> None:
        before = {p.name: p.read_bytes() for p in self.fixture.storage.iterdir()}
        receipt = self.check()
        self.assertTrue(receipt["current_at_check"])
        self.assertFalse(receipt["reusable_authority"])
        self.assertFalse(receipt["execution_authorized"])
        self.assertFalse(receipt["provider_context_loaded"])
        for private in ("Use batch execution.", "PRIVATE-POLICY-PROSE-CANARY"):
            self.assertNotIn(private, json.dumps(receipt))
        self.assertEqual(
            before, {p.name: p.read_bytes() for p in self.fixture.storage.iterdir()}
        )

    def test_guard_yields_only_exact_role_payload(self) -> None:
        self.fixture.input.unlink()
        self.fixture.fixture.brief.unlink()
        with self.store.guard_context(
            self.fixture.workspace,
            self.selection,
            self.fixture.policy_path,
            self.policy_sha,
        ) as context:
            self.assertEqual(context, self.snapshot.context)
            self.assertEqual(
                digest(canonical_bytes(context)), self.selection.context_sha256
            )
            self.assertNotIn(
                "PRIVATE-POLICY-PROSE-CANARY", canonical_bytes(context).decode()
            )

    def test_role_scope_context_and_snapshot_substitutions_reject(self) -> None:
        for field, value in (
            ("role", "judge"),
            ("scope", "Other scope"),
            ("context_sha256", "a" * 64),
            ("snapshot_sha256", "b" * 64),
        ):
            selection = RoleContextSelection.model_validate_json(
                json.dumps(
                    {
                        **self.selection.model_dump(mode="json"),
                        field: value,
                    }
                )
            )
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(selection)

    def test_new_assessment_invalidates_old_packet_even_with_identical_rules(
        self,
    ) -> None:
        self.reassess()
        with self.assertRaisesRegex(ValueError, "no longer current"):
            self.check()
        self.assertTrue(
            self.store.show_context(self.fixture.workspace, self.snapshot.sha256)[
                "historical_snapshot"
            ]
        )

    def test_changed_requirements_and_binding_invalidate_packet(self) -> None:
        self.fixture.fixture.accept(clear=True)
        self.fixture.fixture.accept()
        with self.assertRaises(ValueError):
            self.check()
        self.reassess()
        with self.assertRaises(ValueError):
            self.check()
        self.fixture.attach_advisory()
        with self.assertRaises(ValueError):
            self.check()

    def test_policy_change_rejects_even_when_new_hash_is_selected(self) -> None:
        self.fixture.policy_path.write_text(self.fixture.policy_path.read_text() + " ")
        with self.assertRaises(ValueError):
            self.check()
        self.policy_sha = digest(self.fixture.policy_path.read_bytes())
        with self.assertRaisesRegex(ValueError, "selected policy changed"):
            self.check()

    def test_missing_policy_does_not_fall_back_to_retained_policy(self) -> None:
        self.fixture.policy_path.unlink()
        with self.assertRaises((ValueError, OSError)):
            self.check()
        self.store.show_context(self.fixture.workspace, self.snapshot.sha256)

    def test_external_policy_change_during_local_use_rejects_on_exit(self) -> None:
        with (
            self.assertRaises(ValueError),
            self.store.guard_context(
                self.fixture.workspace,
                self.selection,
                self.fixture.policy_path,
                self.policy_sha,
            ),
        ):
            self.fixture.policy_path.write_text(
                self.fixture.policy_path.read_text() + " "
            )

    def test_external_snapshot_replacement_during_local_use_rejects(self) -> None:
        path = self.fixture.storage / role_snapshot_name(self.snapshot.sha256)
        with (
            self.assertRaises(ValueError),
            self.store.guard_context(
                self.fixture.workspace,
                self.selection,
                self.fixture.policy_path,
                self.policy_sha,
            ),
        ):
            payload = path.read_bytes()
            path.unlink()
            path.write_bytes(payload)
            path.chmod(0o600)

    def test_consumer_failure_releases_lock_and_propagates(self) -> None:
        with (
            self.assertRaisesRegex(RuntimeError, "consumer failure"),
            self.store.guard_context(
                self.fixture.workspace,
                self.selection,
                self.fixture.policy_path,
                self.policy_sha,
            ),
        ):
            raise RuntimeError("consumer failure")
        self.check()

    def test_local_guard_blocks_competing_guidance_writer(self) -> None:
        descriptor = os.open(self.fixture.storage / "memory.lock", os.O_RDWR)
        self.addCleanup(os.close, descriptor)
        with (
            self.store.guard_context(
                self.fixture.workspace,
                self.selection,
                self.fixture.policy_path,
                self.policy_sha,
            ),
            self.assertRaises(BlockingIOError),
        ):
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(descriptor, fcntl.LOCK_UN)

    def test_other_project_and_public_snapshot_reject(self) -> None:
        other = self.fixture.workspace / "nested"
        other.mkdir()
        with self.assertRaises(ValueError):
            self.store.check_context(
                other, self.selection, self.fixture.policy_path, self.policy_sha
            )
        path = self.fixture.storage / role_snapshot_name(self.snapshot.sha256)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.check()

    def test_cli_check_and_stale_rejection(self) -> None:
        args = (
            "check",
            "--snapshot-sha256",
            self.selection.snapshot_sha256,
            "--context-sha256",
            self.selection.context_sha256,
            "--role",
            self.selection.role,
            "--scope",
            self.selection.scope,
            "--policy",
            str(self.fixture.policy_path),
            "--expected-policy-sha256",
            self.policy_sha,
        )
        result = self.fixture.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["current_at_check"])
        self.reassess()
        result = self.fixture.cli(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PRIVATE-POLICY-PROSE-CANARY", result.stdout + result.stderr)

    def test_cli_rejects_missing_or_mutating_options(self) -> None:
        for args in (
            ("check",),
            ("check", "--apply"),
            ("show", "--snapshot-sha256", self.snapshot.sha256, "--role", "coder"),
        ):
            with self.subTest(args=args):
                self.assertNotEqual(self.fixture.cli(*args).returncode, 0)


if __name__ == "__main__":
    unittest.main()
