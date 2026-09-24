"""Authenticated custody and trusted read-only VCS/E2 provenance for G4."""

from __future__ import annotations

import base64
import binascii
import json
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self, cast

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
    verify_implementation_binding_record,
)
from mos_eisley.reviewer_test_execution import KnownControlValidationRecord
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.files import read_bounded
from mos_eisley.run.process import bounded_process

PROVENANCE_ARTIFACT_BYTES = 8_000_000
GIT_OUTPUT_BYTES = 32_000_000
GIT_EXECUTABLE_BYTES = 64_000_000
MAX_CHANGED_PATHS = 512

_CREATOR_DOMAIN = b"mos-eisley/g4-creator-approval/v1\x00"
_REVIEWER_DOMAIN = b"mos-eisley/g4-reviewer-custody/v1\x00"
_ASSIGNMENT_DOMAIN = b"mos-eisley/g4-child-assignment/v1\x00"
_RESULT_DOMAIN = b"mos-eisley/g4-child-result/v1\x00"
_GIT_DOMAIN = b"mos-eisley/g4-git-provenance/v1\x00"

OperatorMode = Literal["separated", "single_operator"]
SourceRevision = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
ObjectId = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
RelativePath = Annotated[str, Field(min_length=1, max_length=4096)]


def _decode_base64(value: str, size: int, label: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"invalid {label} encoding") from None
    if len(raw) != size or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError(f"noncanonical {label} encoding")
    return raw


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("G4 provenance timestamps require explicit UTC")
    return value


def _relative_path(value: str, *, allow_dot: bool = False) -> str:
    if "\\" in value or "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("G4 provenance paths must use canonical POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("G4 provenance paths must remain relative")
    if path.as_posix() != value or (value == "." and not allow_dot):
        raise ValueError("G4 provenance paths must be canonical")
    return value


class G4ProvenanceSigner(Contract):
    signer_id: Identifier
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode_base64(self.public_key_base64, 32, "G4 public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode_base64(self.public_key_base64, 32, "G4 public key"))


def provenance_signer(signer_id: str, key: Ed25519PublicKey) -> G4ProvenanceSigner:
    return G4ProvenanceSigner(
        signer_id=signer_id,
        public_key_base64=base64.b64encode(key.public_bytes_raw()).decode("ascii"),
    )


class G4ProvenanceTrustPolicy(Contract):
    schema_version: Literal[1, 2] = 1
    kind: Literal["g4_provenance_trust_policy"] = "g4_provenance_trust_policy"
    policy_id: Identifier
    creators: Annotated[
        tuple[G4ProvenanceSigner, ...], Field(min_length=1, max_length=8)
    ]
    reviewers: Annotated[
        tuple[G4ProvenanceSigner, ...], Field(min_length=1, max_length=8)
    ]
    vcs_brokers: Annotated[
        tuple[G4ProvenanceSigner, ...], Field(min_length=1, max_length=8)
    ]
    children: Annotated[
        tuple[G4ProvenanceSigner, ...], Field(min_length=1, max_length=32)
    ]
    valid_from: datetime
    valid_until: datetime
    operator_mode: OperatorMode = Field(
        default="separated", exclude_if=lambda value: value == "separated"
    )
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent_roles(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("G4 provenance policy window must be positive")
        groups = (self.creators, self.reviewers, self.vcs_brokers, self.children)
        for group in groups:
            if tuple(item.signer_id for item in group) != tuple(
                sorted(item.signer_id for item in group)
            ):
                raise ValueError("G4 provenance signers must be sorted")
            pairs = tuple((item.signer_id, item.public_key_sha256) for item in group)
            if len(pairs) != len(set(pairs)):
                raise ValueError("G4 provenance signer entries must be unique")
        human = self.creators + self.reviewers + self.vcs_brokers
        if self.operator_mode == "separated":
            if self.schema_version != 1:
                raise ValueError("separated G4 provenance requires schema 1")
            if len({item.signer_id for item in human}) != len(human) or len(
                {item.public_key_sha256 for item in human}
            ) != len(human):
                raise ValueError("separated G4 human roles require distinct signers")
        else:
            pairs = {(item.signer_id, item.public_key_sha256) for item in human}
            if (
                self.schema_version != 2
                or len(self.creators) != 1
                or len(self.reviewers) != 1
                or len(self.vcs_brokers) != 1
                or len(pairs) != 1
            ):
                raise ValueError(
                    "single-operator G4 provenance requires one shared human signer"
                )
        human_ids = {item.signer_id for item in human}
        human_keys = {item.public_key_sha256 for item in human}
        if any(
            item.signer_id in human_ids or item.public_key_sha256 in human_keys
            for item in self.children
        ):
            raise ValueError("G4 child signers must be distinct from human roles")
        if len({item.signer_id for item in self.children}) != len(self.children) or len(
            {item.public_key_sha256 for item in self.children}
        ) != len(self.children):
            raise ValueError("G4 child signers require distinct identities and keys")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4ArtifactSignature(Contract):
    signer_id: Identifier
    public_key_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode_base64(self.signature_base64, 64, "G4 signature")
        return self


class G4CreatorApproval(Contract):
    schema_version: Literal[1, 2] = 1
    kind: Literal["g4_creator_approval"] = "g4_creator_approval"
    approval_id: Identifier
    policy_sha256: Digest
    operator_mode: OperatorMode = Field(
        default="separated", exclude_if=lambda value: value == "separated"
    )
    issued_at: datetime
    approved_plan_sha256: Digest
    creator_test_suite_sha256: Digest
    public_interface_sha256s: Annotated[
        tuple[Digest, ...], Field(min_length=1, max_length=16)
    ]
    rubric_sha256: Digest
    base_revision: SourceRevision
    exact_plan_and_tests_approved: Literal[True] = True
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent_approval(self) -> Self:
        if self.public_interface_sha256s != tuple(
            sorted(self.public_interface_sha256s)
        ):
            raise ValueError("approved interface digests must be sorted")
        if len(self.public_interface_sha256s) != len(
            set(self.public_interface_sha256s)
        ):
            raise ValueError("approved interface digests must be unique")
        if (self.operator_mode == "single_operator") != (self.schema_version == 2):
            raise ValueError("creator approval schema and operator mode differ")
        return self


class SignedG4CreatorApproval(Contract):
    approval: G4CreatorApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4ReviewerCustody(Contract):
    schema_version: Literal[1, 2] = 1
    kind: Literal["g4_reviewer_package_custody"] = "g4_reviewer_package_custody"
    custody_id: Identifier
    policy_sha256: Digest
    operator_mode: OperatorMode = Field(
        default="separated", exclude_if=lambda value: value == "separated"
    )
    issued_at: datetime
    frozen_reviewer_test_package_sha256: Digest
    reviewer_test_payload_sha256: Digest
    creator_approval_artifact_sha256: Digest
    implementation_inspected_before_freeze: Literal[False] = False
    author_telemetry_seen_before_freeze: Literal[False] = False
    package_bytes_retained_exactly: Literal[True] = True
    independent_human_review_claimed: bool
    single_operator_self_review_risk_accepted: bool
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def honest_mode(self) -> Self:
        if self.operator_mode == "single_operator":
            if (
                self.schema_version != 2
                or self.independent_human_review_claimed
                or not self.single_operator_self_review_risk_accepted
            ):
                raise ValueError("single-operator custody must disclose self-review")
        elif (
            self.schema_version != 1
            or not self.independent_human_review_claimed
            or self.single_operator_self_review_risk_accepted
        ):
            raise ValueError("separated custody requires an independence assertion")
        return self


class SignedG4ReviewerCustody(Contract):
    custody: G4ReviewerCustody
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4ChildAssignment(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_bounded_child_assignment"] = "g4_bounded_child_assignment"
    assignment_id: Identifier
    policy_sha256: Digest
    issued_at: datetime
    creator_approval_artifact_sha256: Digest
    reviewer_custody_artifact_sha256: Digest
    frozen_reviewer_test_package_sha256: Digest
    base_revision: SourceRevision
    child_signer_id: Identifier
    child_public_key_sha256: Digest
    child_brief_sha256: Digest
    acceptance_criteria_sha256: Digest
    creator_test_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=MAX_CHANGED_PATHS)
    ]
    owned_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=MAX_CHANGED_PATHS)
    ]
    max_input_tokens: Annotated[int, Field(ge=1, le=10_000_000)]
    max_output_tokens: Annotated[int, Field(ge=1, le=1_000_000)]
    max_tool_calls: Annotated[int, Field(ge=1, le=10_000)]
    max_seconds: Annotated[int, Field(ge=1, le=86_400)]
    max_microusd: Annotated[int, Field(ge=0, le=1_000_000_000)]
    meaningful_implementation_subtask: Literal[True] = True
    creator_test_inventory_complete: Literal[True] = True
    creator_test_mutation_authorized: Literal[False] = False
    reviewer_package_mutation_authorized: Literal[False] = False
    git_metadata_access_authorized: Literal[False] = False
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("creator_test_paths", "owned_paths")
    @classmethod
    def canonical_paths(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        checked = tuple(_relative_path(path) for path in paths)
        if checked != tuple(sorted(checked)) or len(checked) != len(set(checked)):
            raise ValueError("child and creator-test paths must be unique and sorted")
        return checked

    @model_validator(mode="after")
    def tests_are_outside_child_scope(self) -> Self:
        if set(self.creator_test_paths) & set(self.owned_paths):
            raise ValueError("child-owned paths must exclude creator tests")
        return self


class SignedG4ChildAssignment(Contract):
    assignment: G4ChildAssignment
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4ChildResult(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_bounded_child_result"] = "g4_bounded_child_result"
    result_id: Identifier
    policy_sha256: Digest
    issued_at: datetime
    assignment_artifact_sha256: Digest
    base_revision: SourceRevision
    child_revision: SourceRevision
    patch_sha256: Digest
    patch_bytes: Annotated[int, Field(ge=1, le=GIT_OUTPUT_BYTES)]
    changed_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=MAX_CHANGED_PATHS)
    ]
    verification_evidence_sha256: Digest
    unresolved_issue_count: Annotated[int, Field(ge=0, le=10_000)]
    creator_tests_modified: Literal[False] = False
    reviewer_package_modified: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("changed_paths")
    @classmethod
    def canonical_paths(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        checked = tuple(_relative_path(path) for path in paths)
        if checked != tuple(sorted(checked)) or len(checked) != len(set(checked)):
            raise ValueError("child changed paths must be unique and sorted")
        return checked


class SignedG4ChildResult(Contract):
    result: G4ChildResult
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class GitBoundFile(Contract):
    binding_path: RelativePath
    repository_path: RelativePath
    mode: Literal["100644", "100755"]
    object_id: ObjectId
    content_sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=2_000_000)]

    @field_validator("binding_path", "repository_path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return _relative_path(value)


class TrustedGitProvenance(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_trusted_git_provenance"] = "g4_trusted_git_provenance"
    repository_id: Identifier
    implementation_prefix: RelativePath
    git_executable_sha256: Digest
    git_version: Annotated[str, Field(min_length=1, max_length=200)]
    object_format: Literal["sha1", "sha256"]
    base_revision: SourceRevision
    child_revision: SourceRevision
    child_tree_id: ObjectId
    source_revision: SourceRevision
    source_tree_id: ObjectId
    binding_record_sha256: Digest
    implementation_tree_sha256: Digest
    child_assignment_artifact_sha256: Digest
    child_result_artifact_sha256: Digest
    child_patch_sha256: Digest
    child_patch_bytes: Annotated[int, Field(ge=1, le=GIT_OUTPUT_BYTES)]
    child_changed_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=MAX_CHANGED_PATHS)
    ]
    files: Annotated[tuple[GitBoundFile, ...], Field(min_length=2, max_length=2048)]
    head_equals_source_revision: Literal[True] = True
    base_is_ancestor_of_child: Literal[True] = True
    child_is_ancestor_of_source: Literal[True] = True
    bound_source_inventory_complete: Literal[True] = True
    bound_blobs_match: Literal[True] = True
    bound_worktree_clean: Literal[True] = True
    vcs_read_completed: Literal[True] = True
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("implementation_prefix")
    @classmethod
    def canonical_prefix(cls, value: str) -> str:
        return _relative_path(value, allow_dot=True)

    @field_validator("child_changed_paths")
    @classmethod
    def canonical_changed_paths(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        checked = tuple(_relative_path(path) for path in paths)
        if checked != tuple(sorted(checked)) or len(checked) != len(set(checked)):
            raise ValueError("Git changed paths must be unique and sorted")
        return checked

    @model_validator(mode="after")
    def sorted_files(self) -> Self:
        paths = tuple(item.binding_path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("Git bound files must be unique and sorted")
        expected_size = 40 if self.object_format == "sha1" else 64
        object_ids = (self.child_tree_id, self.source_tree_id) + tuple(
            item.object_id for item in self.files
        )
        if any(len(value) != expected_size for value in object_ids):
            raise ValueError("Git object IDs differ from repository object format")
        if len(canonical_bytes(self)) > PROVENANCE_ARTIFACT_BYTES:
            raise ValueError("Git provenance exceeds 8 MB")
        return self

    @property
    def provenance_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SignedTrustedGitProvenance(Contract):
    provenance: TrustedGitProvenance
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedG4ProvenanceRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["authenticated_g4_provenance_record"] = (
        "authenticated_g4_provenance_record"
    )
    policy: G4ProvenanceTrustPolicy
    creator_approval: SignedG4CreatorApproval
    reviewer_custody: SignedG4ReviewerCustody
    child_assignment: SignedG4ChildAssignment
    child_result: SignedG4ChildResult
    git_provenance: SignedTrustedGitProvenance
    known_control_record_sha256: Digest
    binding_record_sha256: Digest
    frozen_reviewer_test_package_sha256: Digest
    custody_authenticated: Literal[True] = True
    vcs_provenance_verified: Literal[True] = True
    e2_provenance_verified: Literal[True] = True
    candidate_execution_authorized: Literal[False] = False
    child_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded_record(self) -> Self:
        if len(canonical_bytes(self)) > PROVENANCE_ARTIFACT_BYTES:
            raise ValueError("authenticated G4 provenance record exceeds 8 MB")
        return self

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _signed(
    payload: Contract, signer_id: str, key: Ed25519PrivateKey, domain: bytes
) -> G4ArtifactSignature:
    return G4ArtifactSignature(
        signer_id=signer_id,
        public_key_sha256=digest(key.public_key().public_bytes_raw()),
        signature_base64=base64.b64encode(
            key.sign(domain + canonical_bytes(payload))
        ).decode("ascii"),
    )


def sign_creator_approval(
    approval: G4CreatorApproval, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4CreatorApproval:
    return SignedG4CreatorApproval(
        approval=approval,
        signature=_signed(approval, signer_id, key, _CREATOR_DOMAIN),
    )


def sign_reviewer_custody(
    custody: G4ReviewerCustody, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4ReviewerCustody:
    return SignedG4ReviewerCustody(
        custody=custody,
        signature=_signed(custody, signer_id, key, _REVIEWER_DOMAIN),
    )


def sign_child_assignment(
    assignment: G4ChildAssignment, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4ChildAssignment:
    return SignedG4ChildAssignment(
        assignment=assignment,
        signature=_signed(assignment, signer_id, key, _ASSIGNMENT_DOMAIN),
    )


def sign_child_result(
    result: G4ChildResult, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4ChildResult:
    return SignedG4ChildResult(
        result=result,
        signature=_signed(result, signer_id, key, _RESULT_DOMAIN),
    )


def sign_git_provenance(
    provenance: TrustedGitProvenance, signer_id: str, key: Ed25519PrivateKey
) -> SignedTrustedGitProvenance:
    return SignedTrustedGitProvenance(
        provenance=provenance,
        signature=_signed(provenance, signer_id, key, _GIT_DOMAIN),
    )


def _enrolled(
    policy: G4ProvenanceTrustPolicy,
    role: Literal["creator", "reviewer", "child", "vcs"],
) -> tuple[G4ProvenanceSigner, ...]:
    return {
        "creator": policy.creators,
        "reviewer": policy.reviewers,
        "child": policy.children,
        "vcs": policy.vcs_brokers,
    }[role]


def verify_provenance_signature(
    payload: Contract,
    signature: G4ArtifactSignature,
    policy: G4ProvenanceTrustPolicy,
    role: Literal["creator", "reviewer", "child", "vcs"],
    domain: bytes,
) -> G4ProvenanceSigner:
    candidates = [
        item
        for item in _enrolled(policy, role)
        if item.signer_id == signature.signer_id
        and item.public_key_sha256 == signature.public_key_sha256
    ]
    if len(candidates) != 1:
        raise ValueError(f"G4 {role} signer is not enrolled")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(candidates[0].public_key_base64, 32, "G4 public key")
        ).verify(
            _decode_base64(signature.signature_base64, 64, "G4 signature"),
            domain + canonical_bytes(payload),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError(f"invalid G4 {role} signature") from None
    return candidates[0]


def _issued(policy: G4ProvenanceTrustPolicy, value: datetime) -> None:
    if not policy.valid_from <= value <= policy.valid_until:
        raise ValueError("G4 provenance artifact falls outside its policy window")


def verify_custody_chain(
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    reviewer: SignedG4ReviewerCustody,
    assignment: SignedG4ChildAssignment,
    result: SignedG4ChildResult,
    package: FrozenReviewerTestPackage,
) -> None:
    if (
        creator.approval.policy_sha256 != policy.policy_sha256
        or reviewer.custody.policy_sha256 != policy.policy_sha256
        or assignment.assignment.policy_sha256 != policy.policy_sha256
        or result.result.policy_sha256 != policy.policy_sha256
    ):
        raise ValueError("G4 provenance artifact names a different trust policy")
    if (
        creator.approval.operator_mode != policy.operator_mode
        or reviewer.custody.operator_mode != policy.operator_mode
    ):
        raise ValueError("G4 custody operator modes differ")
    for value in (
        creator.approval.issued_at,
        reviewer.custody.issued_at,
        assignment.assignment.issued_at,
        result.result.issued_at,
    ):
        _issued(policy, value)
    if not (
        creator.approval.issued_at
        <= reviewer.custody.issued_at
        <= assignment.assignment.issued_at
        <= result.result.issued_at
    ):
        raise ValueError("G4 provenance artifact chronology is inconsistent")
    verify_provenance_signature(
        creator.approval, creator.signature, policy, "creator", _CREATOR_DOMAIN
    )
    verify_provenance_signature(
        reviewer.custody, reviewer.signature, policy, "reviewer", _REVIEWER_DOMAIN
    )
    verify_provenance_signature(
        assignment.assignment,
        assignment.signature,
        policy,
        "creator",
        _ASSIGNMENT_DOMAIN,
    )
    child = verify_provenance_signature(
        result.result, result.signature, policy, "child", _RESULT_DOMAIN
    )
    manifest = package.payload.manifest
    references: dict[str, list[str]] = {}
    for reference in manifest.references:
        references.setdefault(reference.kind, []).append(reference.content_sha256)
    expected_interfaces = tuple(sorted(references.get("interface", [])))
    creator_references = tuple(
        item for item in manifest.references if item.kind == "creator_approval"
    )
    if (
        references.get("approved_plan") != [creator.approval.approved_plan_sha256]
        or references.get("rubric") != [creator.approval.rubric_sha256]
        or references.get("creator_approval") != [creator.artifact_sha256]
        or expected_interfaces != creator.approval.public_interface_sha256s
        or len(creator_references) != 1
        or creator_references[0].bytes != len(canonical_bytes(creator))
    ):
        raise ValueError("creator approval differs from frozen package references")
    custody = reviewer.custody
    child_assignment = assignment.assignment
    child_result = result.result
    if (
        custody.frozen_reviewer_test_package_sha256 != package.frozen_package_sha256
        or custody.reviewer_test_payload_sha256 != package.payload_sha256
        or custody.creator_approval_artifact_sha256 != creator.artifact_sha256
        or child_assignment.creator_approval_artifact_sha256 != creator.artifact_sha256
        or child_assignment.reviewer_custody_artifact_sha256 != reviewer.artifact_sha256
        or child_assignment.frozen_reviewer_test_package_sha256
        != package.frozen_package_sha256
        or child_assignment.base_revision != creator.approval.base_revision
        or child_assignment.child_signer_id != child.signer_id
        or child_assignment.child_public_key_sha256 != child.public_key_sha256
        or child_result.assignment_artifact_sha256 != assignment.artifact_sha256
        or child_result.base_revision != child_assignment.base_revision
        or not set(child_result.changed_paths).issubset(child_assignment.owned_paths)
    ):
        raise ValueError("G4 custody or child lineage is inconsistent")


def _git_environment() -> dict[str, str]:
    return {
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
    }


def _git_command(git: Path, arguments: list[str]) -> list[str]:
    return [
        str(git),
        "--no-pager",
        "--no-replace-objects",
        "--literal-pathspecs",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "diff.external=",
        "-c",
        "core.attributesfile=/dev/null",
        *arguments,
    ]


def _git(
    executable: Path,
    root: Path,
    arguments: list[str],
    *,
    limit: int = GIT_OUTPUT_BYTES,
) -> bytes:
    return bounded_process(
        _git_command(executable, arguments),
        timeout=30,
        limit=limit,
        environment=_git_environment(),
        cwd=root,
    )


def _git_text(executable: Path, root: Path, arguments: list[str]) -> str:
    try:
        value = _git(executable, root, arguments, limit=4096).decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Git returned non-UTF-8 metadata") from None
    if value.endswith("\n"):
        value = value[:-1]
    if not value or "\n" in value or "\r" in value:
        raise ValueError("Git returned invalid scalar metadata")
    return value


def _repo_path(prefix: str, relative: str) -> str:
    return relative if prefix == "." else f"{prefix}/{relative}"


def _parse_ls_tree(payload: bytes) -> dict[str, tuple[str, str, str]]:
    result: dict[str, tuple[str, str, str]] = {}
    for entry in payload.split(b"\x00"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, object_id = metadata.decode("ascii").split(" ", 2)
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise ValueError("Git tree output is malformed") from None
        _relative_path(path)
        if path in result:
            raise ValueError("Git tree output contains duplicate paths")
        result[path] = (mode, kind, object_id)
    return result


def _strip_prefix(prefix: str, repository_path: str) -> str:
    path = PurePosixPath(repository_path)
    if prefix == ".":
        return _relative_path(repository_path)
    prefix_path = PurePosixPath(prefix)
    if not path.is_relative_to(prefix_path):
        raise ValueError("child changed a path outside the implementation root")
    return _relative_path(path.relative_to(prefix_path).as_posix())


def record_trusted_git_provenance(
    *,
    repository_id: str,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    binding: ImmutableImplementationBindingRecord,
    reviewer_package_path: Path,
    assignment: SignedG4ChildAssignment,
    result: SignedG4ChildResult,
) -> TrustedGitProvenance:
    root = repository_root.resolve(strict=True)
    implementation = implementation_root.resolve(strict=True)
    if (
        not root.is_dir()
        or not implementation.is_dir()
        or not implementation.is_relative_to(root)
    ):
        raise ValueError("implementation root must be inside the Git repository")
    prefix_path = implementation.relative_to(root)
    prefix = "." if not prefix_path.parts else prefix_path.as_posix()
    _relative_path(prefix, allow_dot=True)
    if not git_executable.is_absolute():
        raise ValueError("trusted Git executable must be absolute")
    executable = git_executable.resolve(strict=True)
    mode = executable.stat().st_mode
    if not stat.S_ISREG(mode) or not os.access(executable, os.X_OK):
        raise ValueError("trusted Git executable must be an executable regular file")
    executable_bytes = read_bounded(executable, GIT_EXECUTABLE_BYTES)

    top = Path(_git_text(executable, root, ["rev-parse", "--show-toplevel"])).resolve()
    if top != root:
        raise ValueError("repository root differs from Git top level")
    object_format = _git_text(executable, root, ["rev-parse", "--show-object-format"])
    if object_format not in {"sha1", "sha256"}:
        raise ValueError("unsupported Git object format")
    expected_length = 40 if object_format == "sha1" else 64
    manifest = binding.payload.manifest
    if len(manifest.source_revision) != expected_length:
        raise ValueError("binding revision differs from Git object format")
    head = _git_text(executable, root, ["rev-parse", "--verify", "HEAD^{commit}"])
    source = _git_text(
        executable,
        root,
        ["rev-parse", "--verify", f"{manifest.source_revision}^{{commit}}"],
    )
    if source != manifest.source_revision or head != source:
        raise ValueError("Git HEAD differs from the exact binding revision")
    base = _git_text(
        executable,
        root,
        ["rev-parse", "--verify", f"{assignment.assignment.base_revision}^{{commit}}"],
    )
    child = _git_text(
        executable,
        root,
        ["rev-parse", "--verify", f"{result.result.child_revision}^{{commit}}"],
    )
    if (
        base != assignment.assignment.base_revision
        or child != result.result.child_revision
    ):
        raise ValueError("child lineage revision is not an exact Git commit")
    _git(executable, root, ["merge-base", "--is-ancestor", base, child], limit=0)
    _git(executable, root, ["merge-base", "--is-ancestor", child, source], limit=0)
    if len({base, child, source}) != 3:
        raise ValueError("base, child and source revisions must be distinct")

    patch = _git(
        executable,
        root,
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            base,
            child,
            "--",
        ],
    )
    changed_raw = _git(
        executable,
        root,
        ["diff", "--name-only", "-z", "--no-renames", base, child, "--"],
    )
    changed_repository_paths: list[str] = []
    for raw in changed_raw.split(b"\x00"):
        if not raw:
            continue
        try:
            changed_repository_paths.append(raw.decode("utf-8"))
        except UnicodeDecodeError:
            raise ValueError("child changed a non-UTF-8 path") from None
    changed = tuple(
        sorted(_strip_prefix(prefix, path) for path in changed_repository_paths)
    )
    if (
        not patch
        or not changed
        or len(changed) != len(set(changed))
        or changed != result.result.changed_paths
        or digest(patch) != result.result.patch_sha256
        or len(patch) != result.result.patch_bytes
        or not set(changed).issubset(assignment.assignment.owned_paths)
    ):
        raise ValueError("child Git diff differs from its signed result or scope")

    source_root_paths = [_repo_path(prefix, item) for item in manifest.source_roots]
    tree_entries = _parse_ls_tree(
        _git(
            executable,
            root,
            ["ls-tree", "-r", "-z", "--full-tree", source, "--", *source_root_paths],
        )
    )
    expected_source_paths = {
        _repo_path(prefix, item.path)
        for item in manifest.files
        if item.kind in {"implementation_source", "implementation_resource"}
    }
    if set(tree_entries) != expected_source_paths:
        raise ValueError("Git source-root inventory differs from the binding")

    files: list[GitBoundFile] = []
    for declaration in manifest.files:
        repository_path = _repo_path(prefix, declaration.path)
        if repository_path in tree_entries:
            file_mode, kind, object_id = tree_entries[repository_path]
        else:
            single = _parse_ls_tree(
                _git(
                    executable,
                    root,
                    ["ls-tree", "-z", "--full-tree", source, "--", repository_path],
                )
            )
            if set(single) != {repository_path}:
                raise ValueError("bound metadata file is absent from Git")
            file_mode, kind, object_id = single[repository_path]
        if kind != "blob" or file_mode not in {"100644", "100755"}:
            raise ValueError("bound Git paths must be regular blobs")
        payload = _git(
            executable,
            root,
            ["cat-file", "blob", f"{source}:{repository_path}"],
            limit=declaration.bytes,
        )
        if (
            len(payload) != declaration.bytes
            or digest(payload) != declaration.content_sha256
        ):
            raise ValueError("Git blob differs from the implementation binding")
        files.append(
            GitBoundFile(
                binding_path=declaration.path,
                repository_path=repository_path,
                mode=cast(Literal["100644", "100755"], file_mode),
                object_id=object_id,
                content_sha256=digest(payload),
                bytes=len(payload),
            )
        )

    status_paths = source_root_paths + [
        _repo_path(prefix, item.path)
        for item in manifest.files
        if item.kind in {"dependency_lock", "build_metadata"}
    ]
    status = _git(
        executable,
        root,
        [
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            *status_paths,
        ],
    )
    if status:
        raise ValueError("bound Git worktree paths are not clean")
    verify_implementation_binding_record(
        binding, reviewer_package_path, implementation_root
    )
    if (
        _git_text(executable, root, ["rev-parse", "--verify", "HEAD^{commit}"])
        != source
    ):
        raise ValueError("Git HEAD changed during provenance reconstruction")
    return TrustedGitProvenance(
        repository_id=repository_id,
        implementation_prefix=prefix,
        git_executable_sha256=digest(executable_bytes),
        git_version=_git_text(executable, root, ["version"]),
        object_format=cast(Literal["sha1", "sha256"], object_format),
        base_revision=base,
        child_revision=child,
        child_tree_id=_git_text(executable, root, ["rev-parse", f"{child}^{{tree}}"]),
        source_revision=source,
        source_tree_id=_git_text(executable, root, ["rev-parse", f"{source}^{{tree}}"]),
        binding_record_sha256=binding.binding_record_sha256,
        implementation_tree_sha256=binding.payload.implementation_tree_sha256,
        child_assignment_artifact_sha256=assignment.artifact_sha256,
        child_result_artifact_sha256=result.artifact_sha256,
        child_patch_sha256=digest(patch),
        child_patch_bytes=len(patch),
        child_changed_paths=changed,
        files=tuple(sorted(files, key=lambda item: item.binding_path)),
    )


def verify_signed_git_provenance(
    signed: SignedTrustedGitProvenance,
    policy: G4ProvenanceTrustPolicy,
) -> None:
    verify_provenance_signature(
        signed.provenance, signed.signature, policy, "vcs", _GIT_DOMAIN
    )


def assemble_authenticated_provenance(
    *,
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    reviewer: SignedG4ReviewerCustody,
    assignment: SignedG4ChildAssignment,
    result: SignedG4ChildResult,
    git_provenance: SignedTrustedGitProvenance,
    package: FrozenReviewerTestPackage,
    binding: ImmutableImplementationBindingRecord,
    controls: KnownControlValidationRecord,
) -> AuthenticatedG4ProvenanceRecord:
    verify_custody_chain(policy, creator, reviewer, assignment, result, package)
    verify_signed_git_provenance(git_provenance, policy)
    provenance = git_provenance.provenance
    if (
        provenance.binding_record_sha256 != binding.binding_record_sha256
        or provenance.implementation_tree_sha256
        != binding.payload.implementation_tree_sha256
        or provenance.source_revision != binding.payload.manifest.source_revision
        or provenance.base_revision != assignment.assignment.base_revision
        or provenance.child_revision != result.result.child_revision
        or provenance.child_assignment_artifact_sha256 != assignment.artifact_sha256
        or provenance.child_result_artifact_sha256 != result.artifact_sha256
        or provenance.child_patch_sha256 != result.result.patch_sha256
        or provenance.child_patch_bytes != result.result.patch_bytes
        or provenance.child_changed_paths != result.result.changed_paths
        or package.frozen_package_sha256
        != binding.payload.frozen_reviewer_test_package_sha256
        or controls.frozen_reviewer_test_package_sha256 != package.frozen_package_sha256
        or controls.adapter_sha256 != binding.payload.adapter_sha256
        or not controls.controls_validated
    ):
        raise ValueError("authenticated G4 provenance inputs do not form one lineage")
    return AuthenticatedG4ProvenanceRecord(
        policy=policy,
        creator_approval=creator,
        reviewer_custody=reviewer,
        child_assignment=assignment,
        child_result=result,
        git_provenance=git_provenance,
        known_control_record_sha256=controls.control_record_sha256,
        binding_record_sha256=binding.binding_record_sha256,
        frozen_reviewer_test_package_sha256=package.frozen_package_sha256,
    )


def verify_authenticated_provenance(
    record: AuthenticatedG4ProvenanceRecord,
    *,
    package: FrozenReviewerTestPackage,
    binding: ImmutableImplementationBindingRecord,
    controls: KnownControlValidationRecord,
) -> None:
    expected = assemble_authenticated_provenance(
        policy=record.policy,
        creator=record.creator_approval,
        reviewer=record.reviewer_custody,
        assignment=record.child_assignment,
        result=record.child_result,
        git_provenance=record.git_provenance,
        package=package,
        binding=binding,
        controls=controls,
    )
    if record != expected:
        raise ValueError("authenticated G4 provenance record is not canonical lineage")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def decode_provenance_artifact[T: Contract](payload: bytes, model: type[T]) -> T:
    if len(payload) > PROVENANCE_ARTIFACT_BYTES:
        raise ValueError("G4 provenance artifact exceeds 8 MB")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        value = model.model_validate_json(payload)
        if canonical_bytes(value) != payload:
            raise ValueError("G4 provenance artifact must be canonical")
        return value
    except (ValueError, RecursionError):
        raise ValueError("invalid G4 provenance artifact") from None
