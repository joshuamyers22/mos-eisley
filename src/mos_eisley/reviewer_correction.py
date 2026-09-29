"""Offline, evidence-gated G4 correction cycles; never a child dispatch path."""

from __future__ import annotations

import base64
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import (
    G4CandidateDispatchReceipt,
    open_private_dispatch_store,
    verify_candidate_dispatch_receipt,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    G4ChildAssignment,
    G4ProvenanceSigner,
    OperatorMode,
    RelativePath,
    SourceRevision,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import KnownControlValidationRecord
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage

_TRIAGE_DOMAIN = b"mos-eisley/g4-correction-triage/v1\x00"
_CYCLE_DOMAIN = b"mos-eisley/g4-correction-cycle-approval/v1\x00"
MAX_CYCLES = 2
MAX_RECORD_BYTES = 2_000_000
Disposition = Literal[
    "implementation_defect",
    "test_defect",
    "plan_gap",
    "flaky",
    "infrastructure_error",
    "unresolved",
]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("correction timestamps require explicit UTC")
    return value


class G4CorrectionReviewPolicy(Contract):
    """Configured judge keys for offline triage, separate from the G4 custody keys."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_review_policy"] = "g4_correction_review_policy"
    provenance_policy_sha256: Digest
    judges: Annotated[tuple[G4ProvenanceSigner, ...], Field(min_length=1, max_length=8)]
    valid_from: datetime
    valid_until: datetime
    operator_mode: OperatorMode
    independent_human_review_claimed: bool
    correction_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("correction review policy window must be positive")
        if (
            self.operator_mode == "single_operator"
            and self.independent_human_review_claimed
        ):
            raise ValueError(
                "single-operator correction review cannot claim independence"
            )
        if (
            self.operator_mode == "separated"
            and not self.independent_human_review_claimed
        ):
            raise ValueError("separated correction review must disclose its claim")
        ids = tuple(item.signer_id for item in self.judges)
        keys = tuple(item.public_key_sha256 for item in self.judges)
        if (
            ids != tuple(sorted(ids))
            or len(set(ids)) != len(ids)
            or len(set(keys)) != len(keys)
        ):
            raise ValueError("correction judge roster must be unique and sorted")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4CorrectionReservations(Contract):
    input_tokens: Annotated[int, Field(ge=0, le=100_000_000)]
    output_tokens: Annotated[int, Field(ge=0, le=100_000_000)]
    tool_calls: Annotated[int, Field(ge=0, le=100_000)]
    seconds: Annotated[int, Field(ge=0, le=1_000_000)]
    microusd: Annotated[int, Field(ge=0, le=10_000_000_000)]


class G4CorrectionTaskBudget(Contract):
    initial_assignment_sha256: Digest
    deadline: datetime
    ceiling: G4CorrectionReservations

    @field_validator("deadline")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)


class G4CorrectionFinding(Contract):
    failed_test_id: Annotated[str, Field(min_length=1, max_length=1024)]
    disposition: Disposition
    applicable_clause_sha256: Digest | None = None
    citation_evidence_sha256: Digest | None = None
    violation_evidence_sha256: Digest | None = None

    @model_validator(mode="after")
    def evidence_for_defect(self) -> Self:
        evidence = (
            self.applicable_clause_sha256,
            self.citation_evidence_sha256,
            self.violation_evidence_sha256,
        )
        if self.disposition == "implementation_defect" and any(
            item is None for item in evidence
        ):
            raise ValueError(
                "implementation defect needs clause, citation and violation evidence"
            )
        return self


class G4CorrectionTriage(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_triage"] = "g4_correction_triage"
    task_id: Identifier
    cycle: Annotated[int, Field(ge=1, le=MAX_CYCLES)]
    review_policy_sha256: Digest
    candidate_receipt_sha256: Digest
    reproduction_receipt_sha256: Digest
    critic_review_sha256: Digest
    issued_at: datetime
    findings: Annotated[
        tuple[G4CorrectionFinding, ...], Field(min_length=1, max_length=10_000)
    ]
    full_judge_coverage_attested: Literal[True] = True
    correction_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def sorted_findings(self) -> Self:
        ids = tuple(item.failed_test_id for item in self.findings)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError(
                "correction findings must cover unique sorted test identities"
            )
        if self.candidate_receipt_sha256 == self.reproduction_receipt_sha256:
            raise ValueError("correction reproduction must be a separate execution")
        return self

    @property
    def triage_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SignedG4CorrectionTriage(Contract):
    triage: G4CorrectionTriage
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4CorrectionCycleApproval(Contract):
    """Creator approval of a bounded cycle, not permission to invoke a child."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_cycle_approval"] = "g4_correction_cycle_approval"
    approval_id: Identifier
    task_id: Identifier
    cycle: Annotated[int, Field(ge=1, le=MAX_CYCLES)]
    provenance_policy_sha256: Digest
    triage_artifact_sha256: Digest
    previous_completion_sha256: Digest | None = None
    source_revision: SourceRevision
    approved_plan_sha256: Digest
    creator_test_suite_sha256: Digest
    frozen_reviewer_test_package_sha256: Digest
    task_budget: G4CorrectionTaskBudget
    reserved_before: G4CorrectionReservations
    child_signer_id: Identifier
    owned_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=512)
    ]
    max_input_tokens: Annotated[int, Field(ge=1, le=10_000_000)]
    max_output_tokens: Annotated[int, Field(ge=1, le=1_000_000)]
    max_tool_calls: Annotated[int, Field(ge=1, le=10_000)]
    max_seconds: Annotated[int, Field(ge=1, le=86_400)]
    max_microusd: Annotated[int, Field(ge=0, le=1_000_000_000)]
    issued_at: datetime
    expires_at: datetime
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("owned_paths")
    @classmethod
    def canonical_paths(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        for value in paths:
            path = PurePosixPath(value)
            if (
                not value
                or "\\" in value
                or "\x00" in value
                or "\n" in value
                or "\r" in value
                or path.is_absolute()
                or ".." in path.parts
                or path.as_posix() != value
                or value == "."
            ):
                raise ValueError(
                    "correction owned paths must be canonical and relative"
                )
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("correction owned paths must be unique and sorted")
        return paths

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if (
            not self.issued_at < self.expires_at
            or self.expires_at - self.issued_at > timedelta(hours=24)
        ):
            raise ValueError(
                "correction approval window must be positive and at most 24 hours"
            )
        if (self.cycle == 1) != (self.previous_completion_sha256 is None):
            raise ValueError("correction cycle does not match previous completion")
        return self


class SignedG4CorrectionCycleApproval(Contract):
    approval: G4CorrectionCycleApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4CorrectionCycleAdmission(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_cycle_admission"] = "g4_correction_cycle_admission"
    triage: SignedG4CorrectionTriage
    approval: SignedG4CorrectionCycleApproval
    candidate_receipt_sha256: Digest
    reproduction_receipt_sha256: Digest
    provenance_record_sha256: Digest
    binding_record_sha256: Digest
    adapter_sha256: Digest
    frozen_reviewer_test_package_sha256: Digest
    previous_completion_sha256: Digest | None = None
    admitted_at: datetime
    cycle_claimed: Literal[True] = True
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("admitted_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def exact_links(self) -> Self:
        if (
            self.triage.triage.task_id != self.approval.approval.task_id
            or self.triage.triage.cycle != self.approval.approval.cycle
            or self.approval.approval.triage_artifact_sha256
            != self.triage.artifact_sha256
            or self.candidate_receipt_sha256
            != self.triage.triage.candidate_receipt_sha256
            or self.reproduction_receipt_sha256
            != self.triage.triage.reproduction_receipt_sha256
            or self.previous_completion_sha256
            != self.approval.approval.previous_completion_sha256
            or self.frozen_reviewer_test_package_sha256
            != self.approval.approval.frozen_reviewer_test_package_sha256
        ):
            raise ValueError("correction admission identities differ")
        if len(canonical_bytes(self)) > MAX_RECORD_BYTES:
            raise ValueError("correction admission exceeds 2 MB")
        return self

    @property
    def admission_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4CorrectionCycleCompletion(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_cycle_completion"] = "g4_correction_cycle_completion"
    admission: G4CorrectionCycleAdmission
    next_provenance_sha256: Digest
    next_candidate_receipt_sha256: Digest
    next_source_revision: SourceRevision
    candidate_tests_passed: bool
    final_review_required: Literal[True] = True
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if (
            self.next_source_revision
            == self.admission.approval.approval.source_revision
        ):
            raise ValueError("correction did not produce a new source revision")
        if len(canonical_bytes(self)) > MAX_RECORD_BYTES:
            raise ValueError("correction completion exceeds 2 MB")
        return self

    @property
    def completion_sha256(self) -> str:
        return digest(canonical_bytes(self))


def decode_correction_artifact[T: Contract](payload: bytes, model: type[T]) -> T:
    """Require bounded, canonical JSON with no duplicate object keys."""
    if len(payload) > MAX_RECORD_BYTES:
        raise ValueError("G4 correction artifact exceeds 2 MB")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate correction artifact key")
            result[key] = value
        return result

    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        value = model.model_validate_json(payload)
        if payload != canonical_bytes(value):
            raise ValueError("G4 correction artifact must be canonical")
        return value
    except (ValueError, RecursionError):
        raise ValueError("invalid G4 correction artifact") from None


def _sign(
    payload: Contract, signer_id: str, key: Ed25519PrivateKey, domain: bytes
) -> G4ArtifactSignature:
    return G4ArtifactSignature(
        signer_id=signer_id,
        public_key_sha256=digest(key.public_key().public_bytes_raw()),
        signature_base64=base64.b64encode(
            key.sign(domain + canonical_bytes(payload))
        ).decode("ascii"),
    )


def sign_correction_triage(
    triage: G4CorrectionTriage, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4CorrectionTriage:
    """External enrolled judge signing primitive; production CLI never takes keys."""
    return SignedG4CorrectionTriage(
        triage=triage, signature=_sign(triage, signer_id, key, _TRIAGE_DOMAIN)
    )


def sign_correction_cycle_approval(
    approval: G4CorrectionCycleApproval, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4CorrectionCycleApproval:
    """External enrolled creator signing primitive; production CLI never takes keys."""
    return SignedG4CorrectionCycleApproval(
        approval=approval, signature=_sign(approval, signer_id, key, _CYCLE_DOMAIN)
    )


def _verify_triage_signature(
    signed: SignedG4CorrectionTriage, policy: G4CorrectionReviewPolicy
) -> None:
    if signed.triage.review_policy_sha256 != policy.policy_sha256:
        raise ValueError("correction triage names a different review policy")
    signer = next(
        (
            item
            for item in policy.judges
            if item.signer_id == signed.signature.signer_id
        ),
        None,
    )
    if signer is None or signed.signature.public_key_sha256 != signer.public_key_sha256:
        raise ValueError("correction judge is not enrolled")
    key = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(signer.public_key_base64, validate=True)
    )
    try:
        key.verify(
            base64.b64decode(signed.signature.signature_base64, validate=True),
            _TRIAGE_DOMAIN + canonical_bytes(signed.triage),
        )
    except InvalidSignature:
        raise ValueError("correction triage signature is invalid") from None


def _verify_failed_pair(
    first: G4CandidateDispatchReceipt, replay: G4CandidateDispatchReceipt
) -> tuple[str, ...]:
    left = first.execution.observation
    right = replay.execution.observation
    if first.candidate_tests_passed or replay.candidate_tests_passed:
        raise ValueError("correction requires two failed candidate runs")
    if first.admission.admitted_at >= replay.admission.admitted_at:
        raise ValueError("correction reproduction must follow the first candidate")
    if (
        first.admission.approval.artifact_sha256
        == replay.admission.approval.artifact_sha256
        or first.admission.request.execution_id == replay.admission.request.execution_id
    ):
        raise ValueError(
            "correction reproduction requires independent one-use execution identities"
        )
    if (
        first.admission.authenticated_provenance_sha256
        != replay.admission.authenticated_provenance_sha256
        or first.admission.binding_record_sha256
        != replay.admission.binding_record_sha256
        or first.admission.frozen_reviewer_test_package_sha256
        != replay.admission.frozen_reviewer_test_package_sha256
        or first.admission.request.container_image_id
        != replay.admission.request.container_image_id
        or first.execution.collection_sha256 != replay.execution.collection_sha256
    ):
        raise ValueError("correction reproduction changed source or test inputs")
    if (
        not first.execution.collection_contract_satisfied
        or not replay.execution.collection_contract_satisfied
        or left.schema_version != 2
        or right.schema_version != 2
        or left.failures < 1
        or right.failures < 1
        or left.errors
        or right.errors
        or left.unexpected_successes
        or right.unexpected_successes
        or tuple(sorted(left.failed_test_ids)) != tuple(sorted(right.failed_test_ids))
        or left.collected_test_ids_sha256 != right.collected_test_ids_sha256
        or left.executed_test_ids_sha256 != right.executed_test_ids_sha256
    ):
        raise ValueError("correction needs matching reproduced assertion failures")
    return tuple(sorted(left.failed_test_ids))


def _claim_name(task_id: str, cycle: int) -> str:
    return f"{digest(f'{task_id}\x00{cycle}'.encode())}.correction-claim"


def _assignment_reservations(
    assignment: G4ChildAssignment,
) -> G4CorrectionReservations:
    return G4CorrectionReservations(
        input_tokens=assignment.max_input_tokens,
        output_tokens=assignment.max_output_tokens,
        tool_calls=assignment.max_tool_calls,
        seconds=assignment.max_seconds,
        microusd=assignment.max_microusd,
    )


def _reserve(
    before: G4CorrectionReservations, grant: G4CorrectionCycleApproval
) -> G4CorrectionReservations:
    return G4CorrectionReservations(
        input_tokens=before.input_tokens + grant.max_input_tokens,
        output_tokens=before.output_tokens + grant.max_output_tokens,
        tool_calls=before.tool_calls + grant.max_tool_calls,
        seconds=before.seconds + grant.max_seconds,
        microusd=before.microusd + grant.max_microusd,
    )


def _completion_name(task_id: str, cycle: int) -> str:
    return f"{digest(f'{task_id}\x00{cycle}'.encode())}.correction-completion"


def _write_claim(store: Path, admission: G4CorrectionCycleAdmission) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _claim_name(
                admission.approval.approval.task_id, admission.approval.approval.cycle
            ),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(admission))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_claim(store: Path, admission: G4CorrectionCycleAdmission) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _claim_name(
                admission.approval.approval.task_id, admission.approval.approval.cycle
            ),
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise ValueError("correction claim is not a private regular file")
            actual = stream.read(MAX_RECORD_BYTES + 1)
        if actual != canonical_bytes(admission):
            raise ValueError("correction claim differs from admission")
    finally:
        os.close(fd)


def verify_correction_cycle_claim(
    store: Path, admission: G4CorrectionCycleAdmission
) -> None:
    """Replay a persisted, private one-use correction-cycle claim."""
    _verify_claim(store, admission)


def _write_completion(store: Path, completion: G4CorrectionCycleCompletion) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _completion_name(
                completion.admission.approval.approval.task_id,
                completion.admission.approval.approval.cycle,
            ),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(completion))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_completion(store: Path, completion: G4CorrectionCycleCompletion) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _completion_name(
                completion.admission.approval.approval.task_id,
                completion.admission.approval.approval.cycle,
            ),
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise ValueError("correction completion is not a private regular file")
            actual = stream.read(MAX_RECORD_BYTES + 1)
        if actual != canonical_bytes(completion):
            raise ValueError("correction completion differs from stored bytes")
    finally:
        os.close(fd)


def admit_correction_cycle(
    *,
    first: G4CandidateDispatchReceipt,
    reproduction: G4CandidateDispatchReceipt,
    triage: SignedG4CorrectionTriage,
    approval: SignedG4CorrectionCycleApproval,
    review_policy: G4CorrectionReviewPolicy,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    binding: ImmutableImplementationBindingRecord,
    package: FrozenReviewerTestPackage,
    reviewer_package_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    dispatch_store: Path,
    correction_store: Path,
    previous: G4CorrectionCycleCompletion | None = None,
    now: datetime | None = None,
) -> G4CorrectionCycleAdmission:
    """Claim one of at most two cycles after exact replay and signed adjudication."""
    current = _utc(now if now is not None else datetime.now(UTC))
    root = repository_root.resolve()
    if any(
        path.resolve().is_relative_to(root)
        for path in (dispatch_store, correction_store, reviewer_package_path)
    ):
        raise ValueError("correction state must remain outside Git")
    for receipt in (first, reproduction):
        verify_candidate_dispatch_receipt(
            receipt,
            dispatch_store=dispatch_store,
            provenance=provenance,
            controls=controls,
            binding=binding,
            package=package,
            reviewer_package_path=reviewer_package_path,
            repository_root=repository_root,
            implementation_root=implementation_root,
            git_executable=git_executable,
        )
    failed_ids = _verify_failed_pair(first, reproduction)
    decision = triage.triage
    grant = approval.approval
    if (
        review_policy.provenance_policy_sha256 != provenance.policy.policy_sha256
        or review_policy.operator_mode != provenance.policy.operator_mode
        or not review_policy.valid_from
        <= decision.issued_at
        <= current
        <= review_policy.valid_until
        or decision.issued_at < reproduction.admission.admitted_at
        or decision.candidate_receipt_sha256 != first.receipt_sha256
        or decision.reproduction_receipt_sha256 != reproduction.receipt_sha256
        or tuple(item.failed_test_id for item in decision.findings) != failed_ids
    ):
        raise ValueError("correction triage does not cover current reproduced failures")
    if review_policy.operator_mode == "separated":
        human_keys = {
            item.public_key_sha256
            for item in (
                provenance.policy.creators
                + provenance.policy.reviewers
                + provenance.policy.vcs_brokers
            )
        }
        if any(item.public_key_sha256 in human_keys for item in review_policy.judges):
            raise ValueError(
                "separated correction judge must be distinct from custody roles"
            )
    child_keys = {item.public_key_sha256 for item in provenance.policy.children}
    if any(item.public_key_sha256 in child_keys for item in review_policy.judges):
        raise ValueError("correction judge must be distinct from coding children")
    _verify_triage_signature(triage, review_policy)
    if any(item.disposition != "implementation_defect" for item in decision.findings):
        raise ValueError(
            "non-implementation finding requires a separate disposition path"
        )
    verify_provenance_signature(
        grant, approval.signature, provenance.policy, "creator", _CYCLE_DOMAIN
    )
    original = provenance.creator_approval.approval
    assignment = provenance.child_assignment.assignment
    source = provenance.git_provenance.provenance
    budget = grant.task_budget
    if (
        grant.task_id != decision.task_id
        or grant.cycle != decision.cycle
        or grant.provenance_policy_sha256 != provenance.policy.policy_sha256
        or grant.triage_artifact_sha256 != triage.artifact_sha256
        or grant.source_revision != source.source_revision
        or grant.approved_plan_sha256 != original.approved_plan_sha256
        or grant.creator_test_suite_sha256 != original.creator_test_suite_sha256
        or grant.frozen_reviewer_test_package_sha256 != package.frozen_package_sha256
        or grant.child_signer_id != assignment.child_signer_id
        or not set(grant.owned_paths) <= set(assignment.owned_paths)
        or set(grant.owned_paths) & set(assignment.creator_test_paths)
        or grant.max_input_tokens > assignment.max_input_tokens
        or grant.max_output_tokens > assignment.max_output_tokens
        or grant.max_tool_calls > assignment.max_tool_calls
        or grant.max_seconds > assignment.max_seconds
        or grant.max_microusd > assignment.max_microusd
        or current > budget.deadline
        or grant.expires_at > budget.deadline
        or not decision.issued_at
        <= grant.issued_at
        <= current
        <= grant.expires_at
        <= provenance.policy.valid_until
    ):
        raise ValueError("correction approval exceeds reviewed source, scope or budget")
    if previous is None:
        if grant.cycle != 1 or grant.previous_completion_sha256 is not None:
            raise ValueError("first correction cycle must have no predecessor")
        if (
            budget.initial_assignment_sha256
            != provenance.child_assignment.artifact_sha256
            or grant.reserved_before != _assignment_reservations(assignment)
        ):
            raise ValueError("correction task budget omits the initial child allowance")
    else:
        _verify_completion(correction_store, previous)
        _verify_claim(correction_store, previous.admission)
        prior_grant = previous.admission.approval.approval
        if budget != prior_grant.task_budget or grant.reserved_before != _reserve(
            prior_grant.reserved_before, prior_grant
        ):
            raise ValueError("correction task budget or carried allowance changed")
    reserved_after = _reserve(grant.reserved_before, grant)
    ceiling = budget.ceiling
    if any(
        used > limit
        for used, limit in (
            (reserved_after.input_tokens, ceiling.input_tokens),
            (reserved_after.output_tokens, ceiling.output_tokens),
            (reserved_after.tool_calls, ceiling.tool_calls),
            (reserved_after.seconds, ceiling.seconds),
            (reserved_after.microusd, ceiling.microusd),
        )
    ):
        raise ValueError("correction exceeds the aggregate task allowance")
    if previous is not None and (
        grant.cycle != previous.admission.approval.approval.cycle + 1
        or grant.task_id != previous.admission.approval.approval.task_id
        or grant.previous_completion_sha256 != previous.completion_sha256
        or previous.candidate_tests_passed
        or previous.next_candidate_receipt_sha256 != first.receipt_sha256
        or previous.next_source_revision != source.source_revision
    ):
        raise ValueError("correction cycle history is stale or exhausted")
    admission = G4CorrectionCycleAdmission(
        triage=triage,
        approval=approval,
        candidate_receipt_sha256=first.receipt_sha256,
        reproduction_receipt_sha256=reproduction.receipt_sha256,
        provenance_record_sha256=provenance.record_sha256,
        binding_record_sha256=binding.binding_record_sha256,
        adapter_sha256=binding.payload.adapter_sha256,
        frozen_reviewer_test_package_sha256=package.frozen_package_sha256,
        previous_completion_sha256=grant.previous_completion_sha256,
        admitted_at=current,
    )
    _write_claim(correction_store, admission)
    return admission


def complete_correction_cycle(
    admission: G4CorrectionCycleAdmission,
    *,
    correction_store: Path,
    next_candidate: G4CandidateDispatchReceipt,
    next_provenance: AuthenticatedG4ProvenanceRecord,
    next_controls: KnownControlValidationRecord,
    next_binding: ImmutableImplementationBindingRecord,
    next_package: FrozenReviewerTestPackage,
    next_reviewer_package_path: Path,
    next_dispatch_store: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    prior_provenance: AuthenticatedG4ProvenanceRecord,
    prior_package: FrozenReviewerTestPackage,
    prior_binding: ImmutableImplementationBindingRecord,
) -> G4CorrectionCycleCompletion:
    """Replay a fresh full custody/Git/candidate chain; never accept the code."""
    root = repository_root.resolve()
    if any(
        path.resolve().is_relative_to(root)
        for path in (correction_store, next_dispatch_store, next_reviewer_package_path)
    ):
        raise ValueError("correction state must remain outside Git")
    _verify_claim(correction_store, admission)
    verify_candidate_dispatch_receipt(
        next_candidate,
        dispatch_store=next_dispatch_store,
        provenance=next_provenance,
        controls=next_controls,
        binding=next_binding,
        package=next_package,
        reviewer_package_path=next_reviewer_package_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
    )
    grant = admission.approval.approval
    old_creator = prior_provenance.creator_approval.approval
    new_creator = next_provenance.creator_approval.approval
    old_source = prior_provenance.git_provenance.provenance.source_revision
    new_source = next_provenance.git_provenance.provenance.source_revision
    new_assignment = next_provenance.child_assignment.assignment
    old_references = tuple(
        item
        for item in prior_package.payload.manifest.references
        if item.kind != "creator_approval"
    )
    new_references = tuple(
        item
        for item in next_package.payload.manifest.references
        if item.kind != "creator_approval"
    )
    if (
        prior_provenance.record_sha256 != admission.provenance_record_sha256
        or prior_binding.binding_record_sha256 != admission.binding_record_sha256
        or prior_binding.payload.adapter_sha256 != admission.adapter_sha256
        or prior_package.frozen_package_sha256
        != admission.frozen_reviewer_test_package_sha256
        or grant.source_revision != old_source
        or next_provenance.policy.policy_sha256 != prior_provenance.policy.policy_sha256
        or new_creator.base_revision != old_source
        or not grant.issued_at <= new_creator.issued_at <= grant.expires_at
        or new_creator.approved_plan_sha256 != grant.approved_plan_sha256
        or new_creator.creator_test_suite_sha256 != grant.creator_test_suite_sha256
        or new_creator.public_interface_sha256s != old_creator.public_interface_sha256s
        or new_creator.rubric_sha256 != old_creator.rubric_sha256
        or next_package.payload.files != prior_package.payload.files
        or next_package.payload.manifest.collection
        != prior_package.payload.manifest.collection
        or new_references != old_references
        or next_binding.payload.manifest.source_roots
        != prior_binding.payload.manifest.source_roots
        or next_binding.payload.manifest.adapter
        != prior_binding.payload.manifest.adapter
        or tuple(
            item
            for item in next_binding.payload.manifest.files
            if item.kind in {"dependency_lock", "build_metadata"}
        )
        != tuple(
            item
            for item in prior_binding.payload.manifest.files
            if item.kind in {"dependency_lock", "build_metadata"}
        )
        or new_assignment.child_signer_id != grant.child_signer_id
        or new_assignment.creator_test_paths
        != prior_provenance.child_assignment.assignment.creator_test_paths
        or not set(new_assignment.owned_paths) <= set(grant.owned_paths)
        or new_assignment.max_input_tokens > grant.max_input_tokens
        or new_assignment.max_output_tokens > grant.max_output_tokens
        or new_assignment.max_tool_calls > grant.max_tool_calls
        or new_assignment.max_seconds > grant.max_seconds
        or new_assignment.max_microusd > grant.max_microusd
        or new_assignment.issued_at < grant.issued_at
        or new_assignment.issued_at > grant.expires_at
        or next_provenance.child_result.result.issued_at > grant.expires_at
        or new_source == old_source
        or next_candidate.admission.admitted_at <= grant.issued_at
        or next_candidate.admission.admitted_at > grant.task_budget.deadline
    ):
        raise ValueError(
            "corrected candidate changed approved tests, scope or cycle lineage"
        )
    completion = G4CorrectionCycleCompletion(
        admission=admission,
        next_provenance_sha256=next_provenance.record_sha256,
        next_candidate_receipt_sha256=next_candidate.receipt_sha256,
        next_source_revision=new_source,
        candidate_tests_passed=next_candidate.candidate_tests_passed,
    )
    _write_completion(correction_store, completion)
    return completion
