"""Difficulty-routing studies are fixed before any outcome is inspected."""

import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Brief, Contract, canonical_bytes
from mos_eisley.core.skills import PromptAsset
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvalCase,
    EvaluationDataset,
    EvaluationGate,
    ExpectedFinding,
    RouteCandidate,
    Split,
    StatisticalDesign,
    SweepPlan,
)
from mos_eisley.evaluation.routing_protocol import (
    CaseFeatureAssignment,
    FeaturePartition,
    ObservablePromptFeatures,
    PromptFeatureManifest,
    RoleRouteConstraint,
    RoutingStudyProtocol,
    SealedRoutingStudy,
    seal_routing_study,
    verify_sealed_routing_study,
)
from mos_eisley.evaluation.scoring import make_plan
from mos_eisley.run.store import private_write


def study_inputs(
    permissive_gate: bool = False,
    max_mean_cost_microusd: int | None = None,
    max_p95_latency_ms: int | None = None,
    routes: tuple[RouteCandidate, ...] | None = None,
) -> tuple[EvaluationDataset, SweepPlan, PromptFeatureManifest, RoutingStudyProtocol]:
    defect = ExpectedFinding(
        id="boundary-defect",
        category="correctness",
        description="The result excludes the boundary value.",
    )
    cases = tuple(
        EvalCase(
            id=f"{split}-{size}-{kind}-{replica}",
            split=cast(Split, split),
            independence_group=f"{split}-{size}-{kind}-{replica}",
            brief=Brief(
                spec=f"Return exact value {index}.",
                diff=f"return {size} value {index} replica {replica}",
            ),
            expected_findings=(defect,) if kind == "defect" else (),
            risk_tags=("public-api",),
        )
        for index, (size, split, kind, replica) in enumerate(
            (size, split, kind, replica)
            for size in ("small", "large")
            for split in ("calibration", "holdout")
            for kind in ("defect", "clean")
            for replica in range(2)
        )
    )
    dataset = EvaluationDataset(id="routing-study", cases=cases)
    selected_routes = routes or (
        RouteCandidate(
            backend="fixture",
            provider="fixture",
            model="economy",
            effort="low",
            client_version="fixture/1",
            registry_sha256="a" * 64,
            prompt=PromptAsset(mode="inline", instructions="Economy review."),
        ),
        RouteCandidate(
            backend="fixture",
            provider="fixture",
            model="fallback",
            effort="high",
            client_version="fixture/1",
            registry_sha256="a" * 64,
            prompt=PromptAsset(mode="inline", instructions="Fallback review."),
        ),
    )
    plan = make_plan(
        dataset,
        CandidateGrid(routes=selected_routes),
        1,
        7,
        EvaluationGate(
            statistical_design=StatisticalDesign(
                min_groups_per_metric=2 if permissive_gate else 30
            ),
            min_detection_lower_bound=0 if permissive_gate else 0.8,
            max_false_positive_upper_bound=1 if permissive_gate else 0.1,
            min_completion_lower_bound=0 if permissive_gate else 0.9,
            max_mean_cost_microusd=max_mean_cost_microusd,
            max_p95_latency_ms=max_p95_latency_ms,
        ),
    )
    assignments = tuple(
        CaseFeatureAssignment(
            case_id=case.id,
            brief_sha256=case.brief.brief_id,
            features=ObservablePromptFeatures(
                role="critic",
                input_bytes=len(canonical_bytes(case.brief)),
                changed_files=1,
                changed_lines=1 if "small" in case.id else 2,
                language_count=1,
                output_contract="critique-v1",
                tool_requirements=("read-file",),
                risk_tags=("public-api",),
            ),
        )
        for case in sorted(dataset.cases, key=lambda item: item.id)
    )
    manifest = PromptFeatureManifest(
        dataset_sha256=dataset.dataset_sha256,
        assignments=assignments,
    )
    candidate_ids = tuple(sorted(route.candidate_id for route in selected_routes))
    protocol = RoutingStudyProtocol(
        study_id="critic-routing-v1",
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        feature_manifest_sha256=manifest.manifest_sha256,
        feature_partition=FeaturePartition(
            input_bytes_upper_bounds=(1024,),
            changed_files_upper_bounds=(1,),
            changed_lines_upper_bounds=(1, 2),
            language_count_upper_bounds=(1,),
        ),
        uncalibrated_action="role_fallback",
        role_constraints=(
            RoleRouteConstraint(
                role="critic",
                minimum_rationale="Both reviewed candidates satisfy the critic floor.",
                permitted_candidate_ids=candidate_ids,
                fallback_candidate_id=selected_routes[1].candidate_id,
            ),
        ),
    )
    return dataset, plan, manifest, protocol


class RoutingProtocolTests(TestCase):
    def test_seals_content_addressed_nonactivating_design(self) -> None:
        dataset, plan, manifest, protocol = study_inputs()
        artifact = seal_routing_study(dataset, plan, manifest, protocol)
        self.assertEqual(artifact.protocol_sha256, protocol.protocol_sha256)
        self.assertEqual(artifact.profile_ids, protocol.profile_ids(manifest))
        self.assertFalse(artifact.activation_authorized)
        self.assertEqual(
            SealedRoutingStudy.model_validate_json(canonical_bytes(artifact)), artifact
        )
        verify_sealed_routing_study(dataset, plan, manifest, artifact)
        changed = artifact.model_copy(update={"profile_ids": ("f" * 64,)})
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            verify_sealed_routing_study(dataset, plan, manifest, changed)

    def test_manifest_recomputes_label_free_dataset_fields(self) -> None:
        dataset, plan, manifest, protocol = study_inputs()
        first = manifest.assignments[0]
        variants = (
            manifest.model_copy(
                update={
                    "assignments": (
                        first.model_copy(update={"brief_sha256": "f" * 64}),
                        *manifest.assignments[1:],
                    )
                }
            ),
            manifest.model_copy(
                update={
                    "assignments": (
                        first.model_copy(
                            update={
                                "features": first.features.model_copy(
                                    update={
                                        "input_bytes": first.features.input_bytes + 1
                                    }
                                )
                            }
                        ),
                        *manifest.assignments[1:],
                    )
                }
            ),
            manifest.model_copy(
                update={
                    "assignments": (
                        first.model_copy(
                            update={
                                "features": first.features.model_copy(
                                    update={"risk_tags": ()}
                                )
                            }
                        ),
                        *manifest.assignments[1:],
                    )
                }
            ),
            manifest.model_copy(update={"assignments": manifest.assignments[1:]}),
        )
        for changed in variants:
            with self.subTest(changed=changed.manifest_sha256):
                changed_protocol = protocol.model_copy(
                    update={"feature_manifest_sha256": changed.manifest_sha256}
                )
                with self.assertRaises(ValueError):
                    seal_routing_study(dataset, plan, changed, changed_protocol)

    def test_profiles_must_support_both_metrics_on_both_splits(self) -> None:
        dataset, plan, manifest, protocol = study_inputs()
        first = next(
            item for item in manifest.assignments if item.features.changed_lines == 1
        )
        changed_features = first.features.model_copy(update={"changed_lines": 3})
        remaining = tuple(item for item in manifest.assignments if item is not first)
        changed = manifest.model_copy(
            update={
                "assignments": tuple(
                    sorted(
                        (
                            first.model_copy(update={"features": changed_features}),
                            *remaining,
                        ),
                        key=lambda item: item.case_id,
                    )
                )
            }
        )
        changed_protocol = protocol.model_copy(
            update={"feature_manifest_sha256": changed.manifest_sha256}
        )
        with self.assertRaisesRegex(ValueError, "clean and defective"):
            seal_routing_study(dataset, plan, changed, changed_protocol)

    def test_role_floors_cannot_reference_unswept_candidates(self) -> None:
        dataset, plan, manifest, protocol = study_inputs()
        changed_constraint = protocol.role_constraints[0].model_copy(
            update={
                "permitted_candidate_ids": ("f" * 64,),
                "fallback_candidate_id": "f" * 64,
            }
        )
        changed = protocol.model_copy(
            update={"role_constraints": (changed_constraint,)}
        )
        with self.assertRaisesRegex(ValueError, "outside the sweep plan"):
            seal_routing_study(dataset, plan, manifest, changed)

    def test_contracts_reject_noncanonical_or_activation_capable_input(self) -> None:
        dataset, plan, manifest, protocol = study_inputs()
        feature = manifest.assignments[0].features
        with self.assertRaises(ValidationError):
            ObservablePromptFeatures.model_validate(
                {
                    **feature.model_dump(),
                    "tool_requirements": ("z-tool", "a-tool"),
                }
            )
        with self.assertRaises(ValidationError):
            RoleRouteConstraint(
                role="critic",
                minimum_rationale="Reviewed floor.",
                permitted_candidate_ids=("a" * 64,),
                fallback_candidate_id="b" * 64,
            )
        with self.assertRaises(ValidationError):
            FeaturePartition(changed_lines_upper_bounds=(10, 5))
        value = seal_routing_study(dataset, plan, manifest, protocol).model_dump(
            mode="json"
        )
        value["activation_authorized"] = True
        with self.assertRaises(ValidationError):
            SealedRoutingStudy.model_validate(value)

    def test_cli_writes_private_sealed_receipt_and_never_overwrites(self) -> None:
        dataset, plan, manifest, protocol = study_inputs()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            values: dict[str, Contract] = {
                "dataset": dataset,
                "plan": plan,
                "manifest": manifest,
                "protocol": protocol,
            }
            paths = {name: root / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))
            output = root / "sealed.json"
            arguments = [
                "eval-seal-routing-study",
                "--dataset",
                str(paths["dataset"]),
                "--plan",
                str(paths["plan"]),
                "--feature-manifest",
                str(paths["manifest"]),
                "--protocol",
                str(paths["protocol"]),
                "--output",
                str(output),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            artifact = SealedRoutingStudy.model_validate_json(output.read_bytes())
            self.assertEqual(event["sealed_study_sha256"], artifact.sealed_study_sha256)
            self.assertFalse(event["activation_authorized"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)
