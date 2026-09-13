"""Require fresh campaign evidence and an independent decision at every launch edge."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    CriticRequest,
    Digest,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import TextBlock
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.run.files import read_bounded
from mos_eisley.run.review_approval import ApprovalPreview
from mos_eisley.run.review_broker import PreparedReviewEnvelope
from mos_eisley.run.review_campaign import (
    CAMPAIGN_BYTES,
    decode_campaign_submission,
    read_campaign_seal,
)
from mos_eisley.run.review_conformance_acceptance import review_role_profile
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
)
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerCriticPreview,
)
from mos_eisley.run.review_launch import (
    ReviewLaunchConfiguration,
    ReviewLaunchPreview,
    decode_launch_configuration,
)
from mos_eisley.run.review_launch_authorization import (
    ReviewLaunchAuthorityPolicy,
    ReviewLaunchScope,
    SignedReviewLaunchDecision,
    verify_review_launch_decision,
)
from mos_eisley.run.review_launch_conformance import check_review_launch_conformance
from mos_eisley.run.store import private_write


class ReviewLaunchBinding(Contract):
    campaign_directory: Annotated[str, Field(min_length=1, max_length=4096)]
    expected_seal_sha256: Digest
    evidence_path: Annotated[str, Field(min_length=1, max_length=4096)]
    expected_evidence_sha256: Digest

    @model_validator(mode="after")
    def absolute_paths(self) -> Self:
        if not all(
            Path(p).is_absolute() for p in (self.campaign_directory, self.evidence_path)
        ):
            raise ValueError(
                "launch admission requires independently selected absolute paths"
            )
        return self


@dataclass(frozen=True)
class ReviewLaunchAdmissionInputs:
    binding: ReviewLaunchBinding
    configuration: ReviewLaunchConfiguration
    authority_policy: Callable[[], ReviewLaunchAuthorityPolicy]
    load_decision: Callable[[], SignedReviewLaunchDecision | None]


class ReviewLaunchAdmission:
    def __init__(
        self,
        inputs: ReviewLaunchAdmissionInputs,
        controller: BrokeredReviewController,
        envelope: PreparedReviewEnvelope,
        reviewer: ModelReviewer,
        *,
        authority_policy: Callable[[], ReviewConformanceAuthorityPolicy],
        runtime: Callable[[], ReviewConformanceRuntime],
    ) -> None:
        self._binding = ReviewLaunchBinding.model_validate_json(
            canonical_bytes(inputs.binding)
        )
        self._configuration = decode_launch_configuration(
            canonical_bytes(inputs.configuration)
        )
        self._policy = inputs.authority_policy
        self._decision = inputs.load_decision
        self._phase_policy = authority_policy
        self._runtime = runtime
        self._controller, self._envelope, self._reviewer = (
            controller,
            envelope,
            reviewer,
        )
        self._signed: SignedReviewLaunchDecision | None = None
        self._recorded = False
        bundle, _ = read_campaign_seal(
            Path(self._binding.campaign_directory), self._binding.expected_seal_sha256
        )
        policy = self._policy()
        evidence_raw = read_bounded(Path(self._binding.evidence_path), CAMPAIGN_BYTES)
        if digest(evidence_raw) != self._binding.expected_evidence_sha256:
            raise ValueError("independently selected launch evidence changed")
        evidence = decode_campaign_submission(evidence_raw)
        evidence_deadlines = [
            min(
                committed.observation_policy.valid_until,
                supplied.signed_observation.observation.observed_at
                + timedelta(
                    seconds=min(
                        bundle.policy.max_observation_age_seconds,
                        committed.observation_policy.max_observation_age_seconds,
                    )
                ),
            )
            for committed, supplied in zip(
                bundle.attempts, evidence.attempts, strict=True
            )
            if supplied is not None
        ]
        self._scope = ReviewLaunchScope(
            launch_authority_policy_sha256=policy.sha256,
            phase_authority_policy_sha256=self._phase_policy().sha256,
            configuration_sha256=digest(canonical_bytes(self._configuration)),
            critic_preview_sha256=digest(canonical_bytes(controller.preview)),
            seal_sha256=self._binding.expected_seal_sha256,
            evidence_file_sha256=self._binding.expected_evidence_sha256,
            runtime=runtime(),
            ledger_path=str(envelope.ledger.path.resolve()),
            artifact_directory=envelope.envelope.artifact_directory,
            max_reserved_microusd=envelope.envelope.total_reserved_microusd,
            expires_at=min(
                policy.valid_until,
                self._phase_policy().valid_until,
                bundle.policy.valid_until,
                envelope.envelope.expires_at,
                *evidence_deadlines,
            ),
        )
        self._fresh(controller.preview)

    @property
    def scope(self) -> ReviewLaunchScope:
        return self._scope

    @property
    def expires_at(self) -> datetime:
        return (
            min(self.scope.expires_at, self._signed.decision.valid_until)
            if self._signed
            else self.scope.expires_at
        )

    @property
    def signed_decision(self) -> SignedReviewLaunchDecision | None:
        return self._signed

    def _fresh(self, preview: ApprovalPreview) -> ReviewLaunchAuthorityPolicy:
        scope, envelope, config = self.scope, self._envelope, self._configuration
        policy = ReviewLaunchAuthorityPolicy.model_validate_json(
            canonical_bytes(self._policy())
        )
        phase_policy = ReviewConformanceAuthorityPolicy.model_validate_json(
            canonical_bytes(self._phase_policy())
        )
        now = datetime.now(UTC)
        if (
            policy.sha256 != scope.launch_authority_policy_sha256
            or phase_policy.sha256 != scope.phase_authority_policy_sha256
            or not policy.valid_from <= now < self.expires_at
            or scope.max_reserved_microusd > policy.max_reserved_microusd
            or self._runtime() != scope.runtime
            or digest(canonical_bytes(self._controller.preview))
            != scope.critic_preview_sha256
            or str(envelope.ledger.path.resolve()) != scope.ledger_path
            or digest(canonical_bytes(envelope.ledger.policy))
            != envelope.envelope.ledger_policy_sha256
            or config.judge_spending != envelope.envelope.judge.spend_policy
            or config.max_total_microusd != envelope.envelope.max_total_microusd
        ):
            raise ValueError(
                "launch admission policy, preview, runtime or spending changed"
            )
        for selected, call in zip(config.critics, envelope.critics, strict=True):
            if (
                call.ledger_path != Path(scope.ledger_path)
                or call.guidance is None
                or selected.spending.policy_sha256
                != call.authorization.spend_policy_sha256
            ):
                raise ValueError(
                    "launch admission requires exact guided spending bindings"
                )
            call.guidance.check()
        directory = Path(scope.artifact_directory)
        if self._controller.start is None and (
            self._controller.phase != "prepared"
            or directory.exists()
            or directory.is_symlink()
        ):
            raise ValueError("launch admission requires an unused owned controller")
        bundle, _ = read_campaign_seal(
            Path(self._binding.campaign_directory), scope.seal_sha256
        )
        forbidden = [
            s
            for p in (phase_policy, *(a.authority_policy for a in bundle.attempts))
            for s in (*p.authorities, *p.observers)
        ]
        if any(
            s.signer_id == other.signer_id or s.key_sha256 == other.key_sha256
            for s in policy.reviewers
            for other in forbidden
        ):
            raise ValueError(
                "launch reviewers must be separate from phase authorities and observers"
            )
        if any(
            Path(a.ledger_path).resolve() == Path(scope.ledger_path)
            or a.preview.envelope.critics[0].ledger_id
            == envelope.envelope.critics[0].ledger_id
            for a in bundle.attempts
        ):
            raise ValueError("launch requires a separate ledger from campaign evidence")
        raw = read_bounded(Path(self._binding.evidence_path), CAMPAIGN_BYTES)
        if digest(raw) != scope.evidence_file_sha256:
            raise ValueError("independently selected launch evidence changed")
        guidance = envelope.envelope.critics[0].guidance_sha256
        if guidance is None:
            raise ValueError("launch admission requires guided preview evidence")
        launch = ReviewLaunchPreview(
            configuration_sha256=scope.configuration_sha256,
            registry_sha256=digest(canonical_bytes(config.registry)),
            guidance_sha256=guidance,
            preview=self._controller.preview,
        )
        reviewed = check_review_launch_conformance(
            config,
            launch,
            Path(self._binding.campaign_directory),
            scope.seal_sha256,
            decode_campaign_submission(raw),
            runtime=scope.runtime,
            now=now,
        )
        if reviewed.conformance.status != "accepted":
            raise ValueError(
                "launch requires all three freshly verified campaign slots"
            )
        request = self._controller.preview.requests[0]
        content = "".join(
            b.text for b in request.turns[0].blocks if isinstance(b, TextBlock)
        )
        brief = CriticRequest.model_validate_json(content).brief
        if (
            review_role_profile(
                self._reviewer.judge_request(JudgeRequest(brief=brief, findings=()))
            )
            != bundle.policy.judge
        ):
            raise ValueError("owning launch judge differs from verified conformance")
        if isinstance(preview, ControllerCriticPreview):
            if digest(canonical_bytes(preview)) != scope.critic_preview_sha256:
                raise ValueError("launch selected another critic preview")
        elif (
            preview.controller_sha256 != self._controller.approval_sha256
            or review_role_profile(preview.model_request) != bundle.policy.judge
        ):
            raise ValueError(
                "launch judge differs from its admitted controller or profile"
            )
        return policy

    def check(self, preview: ApprovalPreview) -> None:
        signed = self._decision()
        if signed is None:
            raise ValueError("launch requires an independent signed decision")
        signed = SignedReviewLaunchDecision.model_validate_json(canonical_bytes(signed))
        policy = self._fresh(preview)
        verify_review_launch_decision(signed, policy, self.scope, datetime.now(UTC))
        if self._signed is not None and canonical_bytes(signed) != canonical_bytes(
            self._signed
        ):
            raise ValueError(
                "selected launch decision changed during the owned attempt"
            )
        self._signed = signed
        if self._controller.start is not None:
            path = Path(self.scope.artifact_directory) / "launch-admission.json"
            raw = canonical_bytes(signed)
            if not self._recorded:
                private_write(path, raw)
                self._recorded = True
            elif read_bounded(path, CAMPAIGN_BYTES) != raw:
                raise ValueError("retained launch admission changed")
