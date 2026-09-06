"""Candidate policy freezing is deterministic, calibration-only, and inert."""

import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.evaluation.routing_calibration import (
    RoutingCalibrationReport,
    score_routing_calibration,
)
from mos_eisley.evaluation.routing_policy import (
    FrozenCandidateRoutingPolicy,
    freeze_candidate_routing_policy,
    verify_frozen_candidate_routing_policy,
)
from mos_eisley.evaluation.routing_protocol import (
    RoutingStudyProtocol,
    SealedRoutingStudy,
    seal_routing_study,
)
from mos_eisley.run.store import private_write
from tests.test_routing_calibration import RoutingCalibrationTests, RoutingLineage
from tests.test_routing_protocol import study_inputs


class FrozenRoutingPolicyTests(TestCase):
    def setUp(self) -> None:
        self.dataset, self.plan, self.manifest, self.protocol = study_inputs(True)
        self.sealed = seal_routing_study(
            self.dataset, self.plan, self.manifest, self.protocol
        )
        self.source = RoutingCalibrationTests()
        self.source.dataset = self.dataset
        self.source.plan = self.plan
        self.source.manifest = self.manifest
        self.source.sealed = self.sealed
        self.lineage = self.source.make_lineage("calibration")
        self.report = self.score(self.sealed, self.lineage)

    def score(
        self, sealed: SealedRoutingStudy, lineage: RoutingLineage
    ) -> RoutingCalibrationReport:
        return score_routing_calibration(
            self.dataset,
            self.plan,
            *lineage,
            self.manifest,
            sealed,
        )

    def freeze(
        self,
        sealed: SealedRoutingStudy,
        lineage: RoutingLineage,
        report: RoutingCalibrationReport,
    ) -> FrozenCandidateRoutingPolicy:
        return freeze_candidate_routing_policy(
            self.dataset,
            self.plan,
            *lineage,
            self.manifest,
            sealed,
            report,
        )

    def verify(self, policy: FrozenCandidateRoutingPolicy) -> None:
        verify_frozen_candidate_routing_policy(
            self.dataset,
            self.plan,
            *self.lineage,
            self.manifest,
            self.sealed,
            self.report,
            policy,
        )

    def changed_protocol(self, **updates: object) -> RoutingStudyProtocol:
        return self.protocol.model_copy(update=updates)

    def test_selects_lowest_cost_quality_eligible_route_deterministically(self) -> None:
        policy = self.freeze(self.sealed, self.lineage, self.report)
        economy = next(route for route in self.plan.routes if route.model == "economy")
        self.assertTrue(
            all(
                item.selected_candidate_id == economy.candidate_id
                for item in policy.decisions
            )
        )
        self.assertTrue(
            all(
                item.basis == "calibrated_quality_and_cost"
                and item.action == "calibrated_route"
                and item.selected_mean_cost_microusd == 1
                for item in policy.decisions
            )
        )
        self.assertEqual(policy.holdout_status, "not_evaluated")
        self.assertFalse(policy.promotion_ready)
        self.assertFalse(policy.activation_authorized)
        self.assertEqual(
            FrozenCandidateRoutingPolicy.model_validate_json(canonical_bytes(policy)),
            policy,
        )
        self.verify(policy)

    def test_any_missing_eligible_cost_forces_sealed_fallback(self) -> None:
        lineage = self.source.make_lineage("calibration", "economy")
        report = self.score(self.sealed, lineage)
        policy = self.freeze(self.sealed, lineage, report)
        economy = next(route for route in self.plan.routes if route.model == "economy")
        fallback = next(
            route for route in self.plan.routes if route.model == "fallback"
        )
        self.assertTrue(
            all(
                item.basis == "incomplete_cost_evidence"
                and item.action == "role_fallback"
                and item.missing_cost_candidate_ids == (economy.candidate_id,)
                and item.selected_candidate_id == fallback.candidate_id
                and item.selected_mean_cost_microusd is None
                for item in policy.decisions
            )
        )

    def test_fail_closed_protocol_never_selects_an_uncalibrated_route(self) -> None:
        protocol = self.changed_protocol(uncalibrated_action="fail_closed")
        sealed = seal_routing_study(self.dataset, self.plan, self.manifest, protocol)
        lineage = self.source.make_lineage("calibration", "economy")
        report = self.score(sealed, lineage)
        policy = self.freeze(sealed, lineage, report)
        self.assertTrue(
            all(
                item.basis == "incomplete_cost_evidence"
                and item.action == "fail_closed"
                and item.selected_route is None
                for item in policy.decisions
            )
        )

    def test_role_floor_excludes_otherwise_eligible_cheaper_route(self) -> None:
        fallback = next(
            route for route in self.plan.routes if route.model == "fallback"
        )
        constraint = self.protocol.role_constraints[0].model_copy(
            update={"permitted_candidate_ids": (fallback.candidate_id,)}
        )
        protocol = self.changed_protocol(role_constraints=(constraint,))
        sealed = seal_routing_study(self.dataset, self.plan, self.manifest, protocol)
        report = self.score(sealed, self.lineage)
        policy = self.freeze(sealed, self.lineage, report)
        economy = next(route for route in self.plan.routes if route.model == "economy")
        self.assertTrue(
            all(
                item.selected_candidate_id == fallback.candidate_id
                and item.excluded_below_floor_candidate_ids == (economy.candidate_id,)
                for item in policy.decisions
            )
        )

    def test_no_eligible_route_uses_fallback_without_claiming_calibration(self) -> None:
        dataset, plan, manifest, protocol = study_inputs(False)
        sealed = seal_routing_study(dataset, plan, manifest, protocol)
        source = RoutingCalibrationTests()
        source.dataset = dataset
        source.plan = plan
        source.manifest = manifest
        source.sealed = sealed
        lineage = source.make_lineage("calibration")
        report = score_routing_calibration(dataset, plan, *lineage, manifest, sealed)
        policy = freeze_candidate_routing_policy(
            dataset, plan, *lineage, manifest, sealed, report
        )
        self.assertTrue(
            all(
                item.basis == "no_quality_eligible_route"
                and item.action == "role_fallback"
                and not item.quality_eligible_candidate_ids
                for item in policy.decisions
            )
        )

    def test_known_cost_gate_failure_is_distinct_from_missing_cost(self) -> None:
        dataset, plan, manifest, protocol = study_inputs(True, 0)
        sealed = seal_routing_study(dataset, plan, manifest, protocol)
        source = RoutingCalibrationTests()
        source.dataset = dataset
        source.plan = plan
        source.manifest = manifest
        source.sealed = sealed
        lineage = source.make_lineage("calibration")
        report = score_routing_calibration(dataset, plan, *lineage, manifest, sealed)
        policy = freeze_candidate_routing_policy(
            dataset, plan, *lineage, manifest, sealed, report
        )
        self.assertTrue(
            all(
                item.basis == "no_cost_eligible_route"
                and item.quality_eligible_candidate_ids
                and not item.selection_eligible_candidate_ids
                and not item.missing_cost_candidate_ids
                for item in policy.decisions
            )
        )

    def test_tampered_report_or_policy_fails_full_recomputation(self) -> None:
        first_profile = self.report.profiles[0]
        first_score = first_profile.scores[0]
        changed_score = first_score.model_copy(update={"eligible": False})
        changed_report = self.report.model_copy(
            update={
                "profiles": (
                    first_profile.model_copy(
                        update={"scores": (changed_score, *first_profile.scores[1:])}
                    ),
                    *self.report.profiles[1:],
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "calibration report provenance"):
            self.freeze(self.sealed, self.lineage, changed_report)
        policy = self.freeze(self.sealed, self.lineage, self.report)
        changed_policy = policy.model_copy(update={"plan_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "candidate routing policy provenance"):
            self.verify(changed_policy)

    def test_schema_cannot_grant_activation_or_invent_selected_metrics(self) -> None:
        policy = self.freeze(self.sealed, self.lineage, self.report)
        value = policy.model_dump(mode="json")
        value["activation_authorized"] = True
        with self.assertRaises(ValidationError):
            FrozenCandidateRoutingPolicy.model_validate(value)

        lineage = self.source.make_lineage("calibration", "economy")
        report = self.score(self.sealed, lineage)
        fallback_policy = self.freeze(self.sealed, lineage, report)
        value = fallback_policy.model_dump(mode="json")
        value["decisions"][0]["selected_mean_cost_microusd"] = 1
        with self.assertRaises(ValidationError):
            FrozenCandidateRoutingPolicy.model_validate(value)
        economy = next(route for route in self.plan.routes if route.model == "economy")
        value = fallback_policy.model_dump(mode="json")
        value["decisions"][0]["fallback_candidate_id"] = economy.candidate_id
        with self.assertRaises(ValidationError):
            FrozenCandidateRoutingPolicy.model_validate(value)

    def test_cli_writes_private_nonactivating_candidate_policy(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (
                batch,
                mapping,
                raw,
                grading,
                resolution,
                grading_policy,
                resolution_policy,
                observations,
            ) = self.lineage
            values: dict[str, Contract] = {
                "dataset": self.dataset,
                "plan": self.plan,
                "batch": batch,
                "mapping": mapping,
                "raw": raw,
                "grading": grading,
                "dual": resolution,
                "observations": observations,
                "grading_policy": grading_policy,
                "resolution_policy": resolution_policy,
                "manifest": self.manifest,
                "sealed": self.sealed,
                "report": self.report,
            }
            paths = {name: root / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))
            output = root / "candidate-policy.json"
            arguments = [
                "eval-freeze-routing-policy",
                "--dataset",
                str(paths["dataset"]),
                "--plan",
                str(paths["plan"]),
                "--batch",
                str(paths["batch"]),
                "--mapping",
                str(paths["mapping"]),
                "--raw-results",
                str(paths["raw"]),
                "--grading-batch",
                str(paths["grading"]),
                "--dual-grading-resolution",
                str(paths["dual"]),
                "--dual-graded-observations",
                str(paths["observations"]),
                "--grading-trust-policy",
                str(paths["grading_policy"]),
                "--resolution-trust-policy",
                str(paths["resolution_policy"]),
                "--feature-manifest",
                str(paths["manifest"]),
                "--sealed-study",
                str(paths["sealed"]),
                "--calibration-report",
                str(paths["report"]),
                "--output",
                str(output),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            policy = FrozenCandidateRoutingPolicy.model_validate_json(
                output.read_bytes()
            )
            self.assertEqual(
                event["candidate_policy_sha256"], policy.candidate_policy_sha256
            )
            self.assertEqual(event["holdout_status"], "not_evaluated")
            self.assertFalse(event["activation_authorized"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.verify(policy)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)
