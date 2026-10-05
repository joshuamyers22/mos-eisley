"""The offline G6 resolver selects exact frozen routes and grants no send authority."""

from datetime import UTC, datetime, timedelta
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.registry import ModelRegistry, ModelSpec
from mos_eisley.core.skills import PromptAsset, SkillIdentity
from mos_eisley.evaluation.models import RouteCandidate
from mos_eisley.evaluation.routing_policy import (
    FrozenCandidateRoutingPolicy,
    FrozenProfileDecision,
)
from mos_eisley.evaluation.routing_protocol import seal_routing_study
from mos_eisley.run.exact_route import (
    ExactRouteDenial,
    ExactRouteRequirements,
    ExactRouteSelection,
    resolve_exact_route,
)
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from tests.test_routing_protocol import study_inputs


class ExactRouteTests(TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 26, 12, tzinfo=UTC)
        self.registry = ModelRegistry(
            models=(
                ModelSpec(
                    provider="fixture",
                    id="economy",
                    context_bytes=100_000,
                    max_output_bytes=10_000,
                    efforts=("low", "medium"),
                    default_effort="low",
                    tool_calling=True,
                    structured_output=True,
                    verification="fixture",
                ),
                ModelSpec(
                    provider="fixture",
                    id="fallback",
                    context_bytes=100_000,
                    max_output_bytes=10_000,
                    efforts=("high",),
                    default_effort="high",
                    tool_calling=True,
                    structured_output=True,
                    verification="fixture",
                ),
            )
        )
        registry_sha256 = digest(canonical_bytes(self.registry))
        self.routes = (
            RouteCandidate(
                backend="fixture",
                provider="fixture",
                model="economy",
                effort="low",
                client_version="fixture/1",
                registry_sha256=registry_sha256,
                prompt=PromptAsset(mode="inline", instructions="Economy review."),
            ),
            RouteCandidate(
                backend="fixture",
                provider="fixture",
                model="fallback",
                effort="high",
                client_version="fixture/1",
                registry_sha256=registry_sha256,
                prompt=PromptAsset(mode="inline", instructions="Fallback review."),
            ),
        )
        self.rebuild()
        self.requirements = ExactRouteRequirements(
            role=self.features.role,
            output_contract=self.features.output_contract,
            tool_requirements=self.features.tool_requirements,
            requires_structured_output=True,
        )

    def rebuild(self) -> None:
        self.dataset, self.plan, self.manifest, self.protocol = study_inputs(
            True, routes=self.routes
        )
        self.sealed = seal_routing_study(
            self.dataset, self.plan, self.manifest, self.protocol
        )
        self.features = self.manifest.assignments[0].features
        self.policy = self.make_policy("calibrated_route")
        self.preflight = self.make_preflight(self.policy)

    def make_policy(
        self, action: str, *, unseen_action: str = "role_fallback"
    ) -> FrozenCandidateRoutingPolicy:
        selected = self.routes[0] if action == "calibrated_route" else self.routes[1]
        ids = tuple(sorted(route.candidate_id for route in self.routes))
        profiles = {
            self.protocol.feature_partition.profile(item.features).profile_id: (
                self.protocol.feature_partition.profile(item.features)
            )
            for item in self.manifest.assignments
        }
        decisions = tuple(
            FrozenProfileDecision(
                profile_id=profile_id,
                profile=profile,
                role=profile.role,
                basis=(
                    "calibrated_quality_and_cost"
                    if action == "calibrated_route"
                    else "no_quality_eligible_route"
                ),
                action=action,  # type: ignore[arg-type]
                considered_candidate_ids=ids,
                fallback_candidate_id=self.routes[1].candidate_id,
                quality_eligible_candidate_ids=(
                    ids if action == "calibrated_route" else ()
                ),
                selection_eligible_candidate_ids=(
                    ids if action == "calibrated_route" else ()
                ),
                selected_candidate_id=(
                    selected.candidate_id if action != "fail_closed" else None
                ),
                selected_route=selected if action != "fail_closed" else None,
                selected_mean_cost_microusd=(
                    1 if action == "calibrated_route" else None
                ),
                selected_p95_latency_ms=(1 if action == "calibrated_route" else None),
            )
            for profile_id, profile in sorted(profiles.items())
        )
        return FrozenCandidateRoutingPolicy(
            uncalibrated_action=unseen_action,  # type: ignore[arg-type]
            sealed_study_sha256=self.sealed.sealed_study_sha256,
            protocol_sha256=self.protocol.protocol_sha256,
            feature_manifest_sha256=self.manifest.manifest_sha256,
            dataset_sha256=self.dataset.dataset_sha256,
            plan_sha256=self.plan.plan_sha256,
            calibration_report_sha256="a" * 64,
            decisions=decisions,
        )

    def make_preflight(
        self, policy: FrozenCandidateRoutingPolicy
    ) -> RoutingRuntimePreflight:
        return RoutingRuntimePreflight(
            candidate_policy_sha256=policy.candidate_policy_sha256,
            promotion_receipt_sha256="b" * 64,
            activation_eligibility_sha256="c" * 64,
            control_anchor_policy_sha256="d" * 64,
            anchored_control_entry_sha256="e" * 64,
            checked_at=self.now,
            valid_until=self.now + timedelta(seconds=30),
            eligible_candidate_ids=tuple(
                sorted(route.candidate_id for route in self.routes)
            ),
            unavailable_action=policy.uncalibrated_action,
        )

    def resolve(self, **updates: object) -> ExactRouteSelection | ExactRouteDenial:
        values: dict[str, object] = {
            "plan": self.plan,
            "sealed_study": self.sealed,
            "policy": self.policy,
            "preflight": self.preflight,
            "features": self.features,
            "requirements": self.requirements,
            "registry": self.registry,
            "installed_backend": "fixture",
            "installed_client_version": "fixture/1",
            "now": self.now,
        }
        values.update(updates)
        return resolve_exact_route(**values)  # type: ignore[arg-type]

    def assert_denied(self, reason: str, **updates: object) -> None:
        result = self.resolve(**updates)
        self.assertIsInstance(result, ExactRouteDenial)
        assert isinstance(result, ExactRouteDenial)
        self.assertEqual(result.reason, reason)
        self.assertNotIn("dispatch_authorized", type(result).model_fields)

    def test_exact_calibrated_route_is_inert(self) -> None:
        result = self.resolve()
        self.assertIsInstance(result, ExactRouteSelection)
        assert isinstance(result, ExactRouteSelection)
        self.assertEqual(result.route, self.routes[0])
        self.assertEqual(result.source, "calibrated_route")
        self.assertEqual(result.registry_verification, "fixture")
        self.assertEqual(
            result.requirements_sha256, self.requirements.requirements_sha256
        )
        self.assertEqual(
            result.profile_id,
            self.protocol.feature_partition.profile(self.features).profile_id,
        )
        self.assertNotIn("dispatch_authorized", type(result).model_fields)
        self.assertNotIn("provider_request", type(result).model_fields)

    def test_frozen_and_unseen_fallback_are_exact(self) -> None:
        self.policy = self.make_policy("role_fallback")
        self.preflight = self.make_preflight(self.policy)
        result = self.resolve()
        self.assertIsInstance(result, ExactRouteSelection)
        assert isinstance(result, ExactRouteSelection)
        self.assertEqual(
            (result.source, result.route), ("policy_fallback", self.routes[1])
        )

        unseen = self.features.model_copy(update={"risk_tags": ("new-risk",)})
        result = self.resolve(features=unseen, requirements=self.requirements)
        self.assertIsInstance(result, ExactRouteSelection)
        assert isinstance(result, ExactRouteSelection)
        self.assertEqual(
            (result.source, result.route), ("unseen_profile_fallback", self.routes[1])
        )

    def test_unseen_profile_and_explicit_fail_closed_deny(self) -> None:
        self.protocol = self.protocol.model_copy(
            update={"uncalibrated_action": "fail_closed"}
        )
        self.sealed = seal_routing_study(
            self.dataset, self.plan, self.manifest, self.protocol
        )
        self.policy = self.make_policy("fail_closed", unseen_action="fail_closed")
        self.preflight = self.make_preflight(self.policy)
        self.assert_denied("policy_fail_closed")
        unseen = self.features.model_copy(update={"risk_tags": ("new-risk",)})
        self.assert_denied("unseen_profile", features=unseen)

    def test_unsupported_effort_never_uses_registry_downgrade(self) -> None:
        downgraded = self.registry.resolve("fixture", "economy", "high")
        self.assertTrue(downgraded.substituted)
        self.assertEqual(downgraded.effort, "medium")
        route = self.routes[0].model_copy(update={"effort": "high"})
        self.replace_route(route)
        self.assert_denied("effort_unsupported")

    def replace_route(self, route: RouteCandidate) -> None:
        self.routes = (route, self.routes[1])
        self.rebuild()

    def replace_registry(self, registry: ModelRegistry) -> None:
        self.registry = registry
        registry_sha256 = digest(canonical_bytes(registry))
        self.routes = tuple(
            route.model_copy(update={"registry_sha256": registry_sha256})
            for route in self.routes
        )
        self.rebuild()

    def test_provenance_expiry_and_eligibility_fail(self) -> None:
        self.assert_denied(
            "provenance_mismatch",
            policy=self.policy.model_copy(update={"plan_sha256": "f" * 64}),
        )
        self.assert_denied("preflight_expired", now=self.preflight.valid_until)
        limited = self.preflight.model_copy(
            update={"eligible_candidate_ids": (self.routes[1].candidate_id,)}
        )
        self.assert_denied("candidate_not_eligible", preflight=limited)

    def test_catalog_backend_client_and_capability_mismatch_fail(self) -> None:
        self.assert_denied("backend_mismatch", installed_backend="other")
        self.assert_denied("client_mismatch", installed_client_version="fixture/2")
        changed = self.registry.model_copy(update={"models": self.registry.models[1:]})
        self.assert_denied("registry_mismatch", registry=changed)
        requirements = self.requirements.model_copy(update={"role": "judge"})
        self.assert_denied("capability_unqualified", requirements=requirements)

    def test_pinned_catalog_missing_model_or_capability_denies(self) -> None:
        no_tool = self.registry.models[0].model_copy(update={"tool_calling": False})
        self.replace_registry(ModelRegistry(models=(no_tool, self.registry.models[1])))
        self.assert_denied("capability_unqualified")

        no_structure = no_tool.model_copy(
            update={"tool_calling": True, "structured_output": False}
        )
        self.replace_registry(
            ModelRegistry(models=(no_structure, self.registry.models[1]))
        )
        self.assert_denied("capability_unqualified")

        self.replace_registry(ModelRegistry(models=(self.registry.models[1],)))
        self.assert_denied("model_missing")

    def test_route_and_prompt_substitution_fail(self) -> None:
        changed = self.routes[0].model_copy(
            update={
                "prompt": PromptAsset(mode="inline", instructions="Changed review.")
            }
        )
        self.assert_changed_frozen_route_denied(changed)
        identity = SkillIdentity(
            source="project",
            name="reviewer",
            kind="persona",
            package_sha256="a" * 64,
            instructions_sha256=digest(b"Skill review."),
        )
        skill = PromptAsset(mode="skill", instructions="Skill review.", skill=identity)
        changed = self.routes[0].model_copy(update={"prompt": skill})
        self.assert_changed_frozen_route_denied(changed)

    def test_corrupt_frozen_selection_cannot_use_a_noneligible_candidate(self) -> None:
        decisions = tuple(
            decision.model_copy(update={"selection_eligible_candidate_ids": ()})
            for decision in self.policy.decisions
        )
        policy = self.policy.model_copy(update={"decisions": decisions})
        self.assert_denied(
            "policy_inconsistent",
            policy=policy,
            preflight=self.make_preflight(policy),
        )

    def assert_changed_frozen_route_denied(self, changed: RouteCandidate) -> None:
        decisions = tuple(
            decision.model_copy(update={"selected_route": changed})
            for decision in self.policy.decisions
        )
        policy = self.policy.model_copy(update={"decisions": decisions})
        self.assert_denied(
            "route_identity_mismatch",
            policy=policy,
            preflight=self.make_preflight(policy),
        )

    def test_requirements_reject_duplicate_tools(self) -> None:
        with self.assertRaises(ValidationError):
            ExactRouteRequirements(
                role="critic",
                output_contract="critique-v1",
                tool_requirements=("read-file", "read-file"),
                requires_structured_output=True,
            )
