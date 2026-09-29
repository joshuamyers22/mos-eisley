"""One-use G4 initial coding-child authority and proposal contracts.

This is distinct from the correction cycle. It grants no host write or tests.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import base64
import os
import stat
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_correction_dispatch import (
    MAX_FILES,
    MAX_JOB_BYTES,
    MAX_OFFER_BYTES,
    G4CorrectionChildSourceFile,
    G4CorrectionChildUsage,
    _read_repository_file,
    _relative_path,
    _source_file,
    creator_test_bundle_sha256,
)
from mos_eisley.reviewer_provenance import (
    _ASSIGNMENT_DOMAIN,
    _CREATOR_DOMAIN,
    _REVIEWER_DOMAIN,
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    RelativePath,
    SignedG4ChildAssignment,
    SignedG4CreatorApproval,
    SignedG4ReviewerCustody,
    SourceRevision,
    _git,
    _git_text,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.isolation import OfflineContainer

_DISPATCH_DOMAIN = b"mos-eisley/g4-initial-child-dispatch/v1\x00"
_PROPOSAL_DOMAIN = b"mos-eisley/g4-initial-child-proposal/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("initial-child timestamps require explicit UTC")
    return value


class G4InitialChildDispatchApproval(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_child_dispatch_approval"] = (
        "g4_initial_child_dispatch_approval"
    )
    dispatch_id: Identifier
    policy_sha256: Digest
    creator_approval_sha256: Digest
    reviewer_custody_sha256: Digest
    assignment_sha256: Digest
    source_revision: SourceRevision
    container_image_id: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    child_signer_id: Identifier
    brief_sha256: Digest
    acceptance_criteria_sha256: Digest
    creator_test_bundle_sha256: Digest
    owned_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=MAX_FILES)
    ]
    issued_at: datetime
    expires_at: datetime
    child_dispatch_authorized: Literal[True] = True
    provider_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("initial-child dispatch window is invalid")
        if tuple(_relative_path(path) for path in self.owned_paths) != tuple(
            sorted(set(self.owned_paths))
        ):
            raise ValueError("initial-child owned paths must be unique and sorted")
        return self


class SignedG4InitialChildDispatchApproval(Contract):
    approval: G4InitialChildDispatchApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_initial_child_dispatch_approval(
    approval: G4InitialChildDispatchApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4InitialChildDispatchApproval:
    return SignedG4InitialChildDispatchApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_DISPATCH_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


def preview_initial_child_offer(
    *,
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    custody: SignedG4ReviewerCustody,
    assignment: SignedG4ChildAssignment,
    package: FrozenReviewerTestPackage,
    approval: SignedG4InitialChildDispatchApproval,
    repository_root: Path,
    git_executable: Path,
    approved_plan: str,
    brief: str,
    acceptance_criteria: str,
    container_image_id: str,
    now: datetime | None = None,
) -> G4InitialChildOffer:
    """Replay signed custody and clean Git bytes without consuming an authority."""
    current = _utc(now if now is not None else datetime.now(UTC))
    order = approval.approval
    task = assignment.assignment
    source = creator.approval
    review = custody.custody
    for value in (source.issued_at, review.issued_at, task.issued_at, order.issued_at):
        if not policy.valid_from <= value < policy.valid_until:
            raise ValueError("initial-child custody lies outside policy window")
    if (
        not source.issued_at
        <= review.issued_at
        <= task.issued_at
        <= order.issued_at
        <= current
    ):
        raise ValueError("initial-child custody chronology differs")
    if current >= min(order.expires_at, policy.valid_until):
        raise ValueError("initial-child dispatch authority expired")
    if order.expires_at > policy.valid_until:
        raise ValueError("initial-child order outlives custody policy")
    verify_provenance_signature(
        source, creator.signature, policy, "creator", _CREATOR_DOMAIN
    )
    verify_provenance_signature(
        review, custody.signature, policy, "reviewer", _REVIEWER_DOMAIN
    )
    verify_provenance_signature(
        task, assignment.signature, policy, "creator", _ASSIGNMENT_DOMAIN
    )
    verify_provenance_signature(
        order, approval.signature, policy, "creator", _DISPATCH_DOMAIN
    )
    child = tuple(
        item for item in policy.children if item.signer_id == task.child_signer_id
    )
    if (
        len(child) != 1
        or child[0].public_key_sha256 != task.child_public_key_sha256
        or source.policy_sha256 != policy.policy_sha256
        or review.policy_sha256 != policy.policy_sha256
        or task.policy_sha256 != policy.policy_sha256
        or order.policy_sha256 != policy.policy_sha256
        or source.operator_mode != policy.operator_mode
        or review.operator_mode != policy.operator_mode
        or review.creator_approval_artifact_sha256 != creator.artifact_sha256
        or review.frozen_reviewer_test_package_sha256 != package.frozen_package_sha256
        or review.reviewer_test_payload_sha256 != package.payload_sha256
        or task.creator_approval_artifact_sha256 != creator.artifact_sha256
        or task.reviewer_custody_artifact_sha256 != custody.artifact_sha256
        or task.frozen_reviewer_test_package_sha256 != package.frozen_package_sha256
        or task.base_revision != source.base_revision
        or order.creator_approval_sha256 != creator.artifact_sha256
        or order.reviewer_custody_sha256 != custody.artifact_sha256
        or order.assignment_sha256 != assignment.artifact_sha256
        or order.source_revision != task.base_revision
        or order.child_signer_id != task.child_signer_id
        or order.container_image_id != container_image_id
        or order.owned_paths != task.owned_paths
        or order.brief_sha256 != digest(brief.encode("utf-8"))
        or order.acceptance_criteria_sha256
        != digest(acceptance_criteria.encode("utf-8"))
        or task.child_brief_sha256 != order.brief_sha256
        or task.acceptance_criteria_sha256 != order.acceptance_criteria_sha256
        or digest(approved_plan.encode("utf-8")) != source.approved_plan_sha256
        or set(task.owned_paths) & set(task.creator_test_paths)
    ):
        raise ValueError("initial-child dispatch differs from approved custody")
    references: dict[str, list[str]] = {}
    for reference in package.payload.manifest.references:
        references.setdefault(reference.kind, []).append(reference.content_sha256)
    if (
        references.get("approved_plan") != [source.approved_plan_sha256]
        or references.get("rubric") != [source.rubric_sha256]
        or references.get("creator_approval") != [creator.artifact_sha256]
        or tuple(sorted(references.get("interface", [])))
        != source.public_interface_sha256s
        or any(
            reference.bytes != len(canonical_bytes(creator))
            for reference in package.payload.manifest.references
            if reference.kind == "creator_approval"
        )
    ):
        raise ValueError("initial-child package differs from approved references")
    if (
        not git_executable.is_absolute()
        or not git_executable.is_file()
        or not os.access(git_executable, os.X_OK)
        or not repository_root.is_absolute()
        or not repository_root.is_dir()
        or repository_root.is_symlink()
    ):
        raise ValueError("initial-child Git executable or repository is invalid")
    root = repository_root.resolve()
    if _git_text(git_executable, root, ["rev-parse", "HEAD"]) != task.base_revision:
        raise ValueError("initial-child repository HEAD differs from assignment")
    if _git(
        git_executable, root, ["status", "--porcelain=v1", "--untracked-files=all"]
    ):
        raise ValueError("initial-child repository has dirty paths")

    def committed_file(path: str) -> G4CorrectionChildSourceFile:
        content = _read_repository_file(root, path)
        committed = _git(
            git_executable, root, ["show", f"HEAD:{path}"], limit=1_000_001
        )
        if content != committed:
            raise ValueError("initial-child source differs from committed Git")
        return _source_file(path, content)

    sources = tuple(committed_file(path) for path in task.owned_paths)
    tests = tuple(committed_file(path) for path in task.creator_test_paths)
    if creator_test_bundle_sha256(tests) != order.creator_test_bundle_sha256:
        raise ValueError("initial-child creator-test view differs from approval")
    if any(stat.S_ISLNK((root / path).lstat().st_mode) for path in task.owned_paths):
        raise ValueError("initial-child source contains a symlink")
    if _git_text(git_executable, root, ["rev-parse", "HEAD"]) != task.base_revision:
        raise ValueError("initial-child repository HEAD changed during preview")
    return G4InitialChildOffer(
        dispatch_approval_sha256=approval.artifact_sha256,
        assignment_sha256=assignment.artifact_sha256,
        source_revision=task.base_revision,
        child_signer_id=task.child_signer_id,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        source_files=sources,
        creator_test_files=tests,
        max_input_tokens=task.max_input_tokens,
        max_output_tokens=task.max_output_tokens,
        max_tool_calls=task.max_tool_calls,
        max_seconds=task.max_seconds,
        max_microusd=task.max_microusd,
    )


class G4InitialChildOffer(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_child_offer"] = "g4_initial_child_offer"
    dispatch_approval_sha256: Digest
    assignment_sha256: Digest
    source_revision: SourceRevision
    child_signer_id: Identifier
    approved_plan: Annotated[str, Field(min_length=1, max_length=64_000)]
    brief: Annotated[str, Field(min_length=1, max_length=32_000)]
    acceptance_criteria: Annotated[str, Field(min_length=1, max_length=32_000)]
    source_files: Annotated[
        tuple[G4CorrectionChildSourceFile, ...],
        Field(min_length=1, max_length=MAX_FILES),
    ]
    creator_test_files: Annotated[
        tuple[G4CorrectionChildSourceFile, ...],
        Field(min_length=1, max_length=MAX_FILES),
    ]
    max_input_tokens: Annotated[int, Field(ge=1, le=10_000_000)]
    max_output_tokens: Annotated[int, Field(ge=1, le=1_000_000)]
    max_tool_calls: Annotated[int, Field(ge=1, le=10_000)]
    max_seconds: Annotated[int, Field(ge=1, le=86_400)]
    max_microusd: Annotated[int, Field(ge=0, le=1_000_000_000)]
    provider_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded(self) -> Self:
        paths = tuple(item.path for item in self.source_files)
        tests = tuple(item.path for item in self.creator_test_files)
        if (
            paths != tuple(sorted(set(paths)))
            or tests != tuple(sorted(set(tests)))
            or set(paths) & set(tests)
            or len(canonical_bytes(self)) > MAX_OFFER_BYTES
        ):
            raise ValueError("initial-child offer paths or size are invalid")
        return self

    @property
    def offer_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4InitialChildProposal(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_child_proposal"] = "g4_initial_child_proposal"
    offer_sha256: Digest
    replacements: Annotated[
        tuple[G4CorrectionChildSourceFile, ...],
        Field(min_length=1, max_length=MAX_FILES),
    ]
    usage: G4CorrectionChildUsage
    unresolved_issue_count: Annotated[int, Field(ge=0, le=10_000)]
    repository_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def sorted_replacements(self) -> Self:
        paths = tuple(item.path for item in self.replacements)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("initial-child replacements must be unique and sorted")
        return self


class SignedG4InitialChildProposal(Contract):
    proposal: G4InitialChildProposal
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_initial_child_proposal(
    proposal: G4InitialChildProposal,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4InitialChildProposal:
    return SignedG4InitialChildProposal(
        proposal=proposal,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_PROPOSAL_DOMAIN + canonical_bytes(proposal))
            ).decode("ascii"),
        ),
    )


class G4InitialChildExecution(Contract):
    offer_sha256: Digest
    proposal_sha256: Digest
    changed_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=MAX_FILES)
    ]
    replacement_tree_sha256: Digest
    usage: G4CorrectionChildUsage
    unresolved_issue_count: Annotated[int, Field(ge=0, le=10_000)]
    host_repository_modified: Literal[False] = False
    acceptance_authorized: Literal[False] = False


class _Tree(Contract):
    files: tuple[tuple[str, Digest], ...]


def validate_initial_child_proposal(
    offer: G4InitialChildOffer,
    signed: SignedG4InitialChildProposal,
    policy: G4ProvenanceTrustPolicy,
) -> G4InitialChildExecution:
    """Validate an enrolled child signature and an exact bounded source proposal."""
    signer = verify_provenance_signature(
        signed.proposal, signed.signature, policy, "child", _PROPOSAL_DOMAIN
    )
    if signer.signer_id != offer.child_signer_id:
        raise ValueError("initial-child proposal signer differs from assignment")
    proposal = signed.proposal
    original = {item.path: item for item in offer.source_files}
    replacements = {item.path: item for item in proposal.replacements}
    if (
        proposal.offer_sha256 != offer.offer_sha256
        or not set(replacements) <= set(original)
        or all(
            original[path].content_sha256 == item.content_sha256
            for path, item in replacements.items()
        )
    ):
        raise ValueError("initial child made no valid owned-path change")
    if any(
        actual > limit
        for actual, limit in (
            (proposal.usage.input_tokens, offer.max_input_tokens),
            (proposal.usage.output_tokens, offer.max_output_tokens),
            (proposal.usage.tool_calls, offer.max_tool_calls),
            (proposal.usage.seconds, offer.max_seconds),
            (proposal.usage.microusd, offer.max_microusd),
        )
    ):
        raise ValueError("initial child exceeded assignment allowance")
    if proposal.usage.tool_calls != 0:
        raise ValueError("initial child tool calls are not supported")
    changed = tuple(
        path
        for path, item in replacements.items()
        if item.content_sha256 != original[path].content_sha256
    )
    tree = tuple(
        (path, replacements.get(path, original[path]).content_sha256)
        for path in sorted(original)
    )
    return G4InitialChildExecution(
        offer_sha256=offer.offer_sha256,
        proposal_sha256=signed.artifact_sha256,
        changed_paths=changed,
        replacement_tree_sha256=digest(canonical_bytes(_Tree(files=tree))),
        usage=proposal.usage,
        unresolved_issue_count=proposal.unresolved_issue_count,
    )


class G4InitialChildDispatchReceipt(Contract):
    approval: SignedG4InitialChildDispatchApproval
    offer: G4InitialChildOffer
    signed_proposal: SignedG4InitialChildProposal
    execution: G4InitialChildExecution
    dispatched_at: datetime
    provider_dispatch_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("dispatched_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def exact_links(self) -> Self:
        if (
            self.approval.artifact_sha256 != self.offer.dispatch_approval_sha256
            or self.approval.approval.assignment_sha256 != self.offer.assignment_sha256
            or self.approval.approval.source_revision != self.offer.source_revision
            or self.approval.approval.child_signer_id != self.offer.child_signer_id
            or self.signed_proposal.proposal.offer_sha256 != self.offer.offer_sha256
            or self.execution.offer_sha256 != self.offer.offer_sha256
            or self.execution.proposal_sha256 != self.signed_proposal.artifact_sha256
            or len(canonical_bytes(self)) > MAX_JOB_BYTES
        ):
            raise ValueError("initial-child receipt links or size are invalid")
        return self

    @property
    def receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4InitialChildJob(Contract):
    offer: G4InitialChildOffer
    signed_proposal: SignedG4InitialChildProposal
    policy: G4ProvenanceTrustPolicy

    @model_validator(mode="after")
    def exact_offer(self) -> Self:
        if (
            self.signed_proposal.proposal.offer_sha256 != self.offer.offer_sha256
            or len(canonical_bytes(self)) > MAX_JOB_BYTES
        ):
            raise ValueError("initial-child job differs from offer or exceeds limit")
        return self


class InitialChildGenerator(Protocol):
    async def generate(
        self, offer: G4InitialChildOffer
    ) -> SignedG4InitialChildProposal: ...


def _claim_initial_dispatch(
    store: Path,
    assignment: SignedG4ChildAssignment,
    approval: SignedG4InitialChildDispatchApproval,
) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            f"{assignment.artifact_sha256}.initial-child-claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(approval))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


async def dispatch_initial_child(
    *,
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    custody: SignedG4ReviewerCustody,
    assignment: SignedG4ChildAssignment,
    package: FrozenReviewerTestPackage,
    approval: SignedG4InitialChildDispatchApproval,
    repository_root: Path,
    git_executable: Path,
    approved_plan: str,
    brief: str,
    acceptance_criteria: str,
    container: OfflineContainer,
    dispatch_store: Path,
    generator: InitialChildGenerator,
    now: datetime | None = None,
) -> G4InitialChildDispatchReceipt:
    """Consume one assignment claim and validate its provider result in containment."""
    current = _utc(now if now is not None else datetime.now(UTC))
    root = repository_root.resolve()
    if dispatch_store.resolve().is_relative_to(
        root
    ) or container.lifecycle_root.resolve().is_relative_to(root):
        raise ValueError("initial-child stores must remain outside repository")
    offer = preview_initial_child_offer(
        policy=policy,
        creator=creator,
        custody=custody,
        assignment=assignment,
        package=package,
        approval=approval,
        repository_root=repository_root,
        git_executable=git_executable,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        container_image_id=container.image_id,
        now=current,
    )
    _claim_initial_dispatch(dispatch_store, assignment, approval)
    duration = min(
        float(offer.max_seconds),
        (approval.approval.expires_at - current).total_seconds(),
        (policy.valid_until - current).total_seconds(),
    )
    if duration <= 0:
        raise ValueError("initial-child dispatch has no remaining time")
    started = time.monotonic()
    async with asyncio.timeout(duration):
        signed = await generator.generate(offer)
    job = G4InitialChildJob(offer=offer, signed_proposal=signed, policy=policy)
    expected = validate_initial_child_proposal(offer, signed, policy)
    remaining = duration - (time.monotonic() - started)
    if remaining <= 0:
        raise TimeoutError("initial-child allowance elapsed")
    output = container.execute(
        ("-m", "mos_eisley.run.reviewer_initial_child"),
        canonical_bytes(job),
        timeout=min(remaining, 60.0),
    )
    if len(output) > 16_384:
        raise ValueError("contained initial-child result exceeds limit")
    actual = G4InitialChildExecution.model_validate_json(output)
    if output != canonical_bytes(actual) or actual != expected:
        raise ValueError("contained initial-child result differs from host replay")
    replay = preview_initial_child_offer(
        policy=policy,
        creator=creator,
        custody=custody,
        assignment=assignment,
        package=package,
        approval=approval,
        repository_root=repository_root,
        git_executable=git_executable,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        container_image_id=container.image_id,
        now=now,
    )
    if replay != offer:
        raise ValueError("initial-child source changed during dispatch")
    return G4InitialChildDispatchReceipt(
        approval=approval,
        offer=offer,
        signed_proposal=signed,
        execution=actual,
        dispatched_at=current,
    )


def verify_initial_child_dispatch_receipt(
    receipt: G4InitialChildDispatchReceipt,
    *,
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    custody: SignedG4ReviewerCustody,
    assignment: SignedG4ChildAssignment,
    package: FrozenReviewerTestPackage,
    repository_root: Path,
    git_executable: Path,
    approved_plan: str,
    brief: str,
    acceptance_criteria: str,
    container: OfflineContainer,
    dispatch_store: Path,
) -> None:
    """Replay the claimed one-use order, source, signature and contained result."""
    if (
        receipt.approval.approval.issued_at > receipt.dispatched_at
        or receipt.dispatched_at >= receipt.approval.approval.expires_at
        or receipt.dispatched_at >= policy.valid_until
    ):
        raise ValueError("initial-child receipt time differs from authority")
    fd = open_private_dispatch_store(dispatch_store)
    try:
        name = f"{assignment.artifact_sha256}.initial-child-claim"
        claim_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise ValueError("initial-child claim is not private")
            claimed = stream.read(16_385)
        if claimed != canonical_bytes(receipt.approval):
            raise ValueError("initial-child claim differs from dispatch order")
    finally:
        os.close(fd)
    offer = preview_initial_child_offer(
        policy=policy,
        creator=creator,
        custody=custody,
        assignment=assignment,
        package=package,
        approval=receipt.approval,
        repository_root=repository_root,
        git_executable=git_executable,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        container_image_id=container.image_id,
        now=receipt.dispatched_at,
    )
    if offer != receipt.offer:
        raise ValueError("initial-child receipt offer differs from source")
    expected = validate_initial_child_proposal(offer, receipt.signed_proposal, policy)
    if expected != receipt.execution:
        raise ValueError("initial-child execution differs from signed proposal")
    job = G4InitialChildJob(
        offer=offer, signed_proposal=receipt.signed_proposal, policy=policy
    )
    output = container.execute(
        ("-m", "mos_eisley.run.reviewer_initial_child"),
        canonical_bytes(job),
        timeout=60.0,
    )
    actual = G4InitialChildExecution.model_validate_json(output)
    if output != canonical_bytes(actual) or actual != expected:
        raise ValueError("initial-child contained replay differs")
