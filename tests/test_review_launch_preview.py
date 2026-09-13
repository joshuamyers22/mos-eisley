"""Launch configuration is explicit, guidance-current, and never live authority."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from test_review_guidance_admission import GuidedBrokerFixture

from mos_eisley.cli import main
from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import ReviewPolicy, canonical_bytes
from mos_eisley.core.registry import openai_registry
from mos_eisley.run.review_launch import (
    CONFIGURATION_BYTES,
    LaunchCritic,
    ReviewLaunchConfiguration,
    decode_launch_configuration,
    prepare_review_launch_preview,
)


class ReviewLaunchTests(GuidedBrokerFixture):
    def setUp(self) -> None:
        super().setUp()
        self.configuration = ReviewLaunchConfiguration(
            registry=openai_registry(),
            critics=(LaunchCritic(critic=self.base.critic, spending=self.base.policy),),
            judge_model=self.base.critic.model,
            judge_spending=self.base.policy,
            effort="medium",
            budget=BudgetPolicy(max_output_tokens=100),
            policy=ReviewPolicy(min_critics=1, min_providers=1),
            max_total_microusd=650,
        )
        self.review_directory = self.base.root / "launch"

    def launch(self, configuration: ReviewLaunchConfiguration | None = None):
        return prepare_review_launch_preview(
            self.configuration if configuration is None else configuration,
            prepared=self.guided.prepared,
            expected_prepared_sha256=self.guided.prepared.sha256,
            workspace=self.guided.fixture.workspace,
            guidance_store=self.guided.store,
            guidance_policy_path=self.guided.fixture.policy_path,
            expected_guidance_policy_sha256=self.guided.policy_sha,
            ledger=self.base.ledger,
            review_directory=self.review_directory,
        )

    def cli_arguments(self):
        config = self.base.root / "launch-config.json"
        config.write_bytes(canonical_bytes(self.configuration))
        prepared = self.base.root / "prepared.json"
        prepared.write_bytes(canonical_bytes(self.guided.prepared))
        return [
            "review-launch-preview",
            "--config",
            str(config),
            "--workspace",
            str(self.guided.fixture.workspace),
            "--guidance-storage",
            str(self.guided.fixture.storage),
            "--prepared",
            str(prepared),
            "--expected-prepared-sha256",
            self.guided.prepared.sha256,
            "--guidance-policy",
            str(self.guided.fixture.policy_path),
            "--expected-guidance-policy-sha256",
            self.guided.policy_sha,
            "--spend-ledger",
            str(self.base.ledger.path),
            "--review-dir",
            str(self.review_directory),
            "--json",
        ]

    def test_exact_guided_preview_preserves_ledger_and_creates_no_run(self):
        before = self.base.ledger.path.read_bytes()
        result = self.launch()
        self.assertEqual(result.preview.envelope.total_reserved_microusd, 650)
        self.assertEqual(result.guidance_sha256, self.guided.prepared.sha256)
        self.assertEqual(
            result.preview.envelope.critics[0].guidance_sha256, result.guidance_sha256
        )
        self.assertIn(b"Use batch execution.", canonical_bytes(result))
        self.assertNotIn(b"PRIVATE-POLICY-PROSE-CANARY", canonical_bytes(result))
        self.assertFalse(result.reservation_created)
        self.assertFalse(result.provider_dispatch_authorized)
        self.assertFalse(result.credential_access_authorized)
        self.assertFalse(result.live_launch_available)
        self.assertEqual(
            result.conformance_status, "review_controller_conformance_required"
        )
        self.assertEqual(before, self.base.ledger.path.read_bytes())
        self.assertFalse(self.review_directory.exists())

    def test_repeated_previews_do_not_consume_spend_or_reuse_attempt_hashes(self):
        first, second = self.launch(), self.launch()
        self.assertNotEqual(first.preview.sha256, second.preview.sha256)
        self.assertEqual(first.configuration_sha256, second.configuration_sha256)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_current_guidance_change_blocks_preparation(self):
        self.invalidate()
        with self.assertRaisesRegex(ValueError, "guidance changed"):
            self.launch()
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_default_diversity_is_not_relaxed_for_openai(self):
        with self.assertRaises(ValueError):
            self.launch(
                self.configuration.model_copy(update={"policy": ReviewPolicy()})
            )
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_aggregate_limit_rejection_leaves_no_partial_reservation(self):
        with self.assertRaises(ValueError):
            self.launch(
                self.configuration.model_copy(update={"max_total_microusd": 649})
            )
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_critic_spend_model_mismatch_rejected(self):
        critic = self.configuration.critics[0].model_copy(
            update={"spending": self.base.policy.model_copy(update={"model": "other"})}
        )
        with self.assertRaises(ValueError):
            self.launch(self.configuration.model_copy(update={"critics": (critic,)}))

    def test_judge_spend_model_mismatch_rejected_before_any_spend(self):
        config = self.configuration.model_copy(
            update={
                "judge_spending": self.base.policy.model_copy(update={"model": "other"})
            }
        )
        with self.assertRaisesRegex(ValueError, "judge spending policy"):
            self.launch(config)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_judge_output_budget_checked_before_critic_admission(self):
        config = self.configuration.model_copy(
            update={
                "judge_spending": self.base.policy.model_copy(
                    update={"max_output_tokens": 99}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "judge output budget"):
            self.launch(config)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_registry_live_label_does_not_grant_conformance_or_launch(self):
        registry = self.configuration.registry.model_copy(
            update={
                "models": tuple(
                    m.model_copy(update={"verification": "live_conformance"})
                    for m in self.configuration.registry.models
                )
            }
        )
        result = self.launch(
            self.configuration.model_copy(update={"registry": registry})
        )
        self.assertFalse(result.live_launch_available)
        self.assertEqual(
            result.conformance_status, "review_controller_conformance_required"
        )

    def test_reasoning_effort_substitution_is_rejected(self):
        registry = self.configuration.registry.model_copy(
            update={
                "models": tuple(
                    m.model_copy(
                        update={"efforts": ("medium",), "default_effort": "medium"}
                    )
                    for m in self.configuration.registry.models
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "substitute reasoning effort"):
            self.launch(
                self.configuration.model_copy(
                    update={"registry": registry, "effort": "high"}
                )
            )

    def test_existing_output_is_preserved(self):
        self.review_directory.write_bytes(b"existing")
        with self.assertRaises(ValueError):
            self.launch()
        self.assertEqual(self.review_directory.read_bytes(), b"existing")

    def test_dangling_output_symlink_rejected(self):
        self.review_directory.symlink_to(self.base.root / "missing")
        with self.assertRaises(ValueError):
            self.launch()
        self.assertFalse((self.base.root / "missing").exists())

    def test_configuration_rejects_duplicate_keys_and_excess_bytes(self):
        raw = canonical_bytes(self.configuration)
        duplicate = b'{"schema_version":1,' + raw[1:]
        for payload in (duplicate, b" " * (CONFIGURATION_BYTES + 1)):
            with self.subTest(size=len(payload)), self.assertRaises(ValueError):
                decode_launch_configuration(payload)

    def test_evaluation_conformance_receipt_cannot_be_substituted(self):
        value = self.configuration.model_dump(mode="json")
        value["conformance"] = {"mode": "authenticated_brokered_evaluation_conformance"}
        with self.assertRaises(ValueError):
            decode_launch_configuration(json.dumps(value).encode())

    def test_cli_has_no_credential_access_or_provider_construction(self):
        args = self.cli_arguments()
        before = self.base.ledger.path.read_bytes()
        output = io.StringIO()
        with (
            redirect_stdout(output),
            patch(
                "mos_eisley.cli._openai_api_key",
                side_effect=AssertionError("credentials"),
            ),
            patch(
                "mos_eisley.providers.openai_responses.AsyncOpenAI",
                side_effect=AssertionError("provider"),
            ),
        ):
            self.assertEqual(main(args), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["type"], "review.launch.preview")
        self.assertFalse(result["live_launch_available"])
        self.assertEqual(before, self.base.ledger.path.read_bytes())
        self.assertFalse(self.review_directory.exists())

    def test_cli_wrong_prepared_pin_rejects_before_reservation(self):
        args = self.cli_arguments()
        args[args.index("--expected-prepared-sha256") + 1] = "f" * 64
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_cli_missing_ledger_does_not_create_a_replacement(self):
        args = self.cli_arguments()
        missing = self.base.root / "missing.sqlite"
        args[args.index("--spend-ledger") + 1] = str(missing)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertFalse(missing.exists())

    def test_expired_judge_pricing_cannot_prepare_a_launch(self):
        policy = self.base.policy.model_copy(
            update={
                "valid_from": datetime.now(UTC) - timedelta(hours=2),
                "valid_until": datetime.now(UTC) - timedelta(hours=1),
            }
        )
        from mos_eisley.core.ports import ProviderError

        with self.assertRaises((ValueError, ProviderError)):
            self.launch(
                self.configuration.model_copy(update={"judge_spending": policy})
            )
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_guidance_is_rechecked_after_request_preparation(self):
        from unittest.mock import PropertyMock

        from mos_eisley.run.review_controller import BrokeredReviewController

        def changed_preview():
            self.invalidate()
            return None

        with patch.object(
            BrokeredReviewController, "preview", new_callable=PropertyMock
        ) as preview:
            preview.side_effect = changed_preview
            with self.assertRaisesRegex(ValueError, "guidance changed"):
                self.launch()
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
