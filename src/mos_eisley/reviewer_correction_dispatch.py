"""One-use, no-host-write dispatch boundary for an approved G4 correction child.

This module deliberately has no provider adapter. A trusted caller supplies a
bounded proposal generator; the child receives only the explicit offer and its
proposed replacements are checked in the immutable offline container.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import os
import stat
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Protocol, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import (
    G4CandidateDispatchReceipt,
    open_private_dispatch_store,
    verify_candidate_dispatch_receipt,
)
from mos_eisley.reviewer_correction import (
    G4CorrectionCycleAdmission,
    verify_correction_cycle_claim,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
    snapshot_implementation_files,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    RelativePath,
    SourceRevision,
    record_trusted_git_provenance,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import KnownControlValidationRecord
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage
from mos_eisley.run.isolation import OfflineContainer

_DOMAIN = b"mos-eisley/g4-correction-child-dispatch/v1\x00"
_PROPOSAL_DOMAIN = b"mos-eisley/g4-correction-child-proposal/v1\x00"
MAX_OFFER_BYTES = 8_000_000
MAX_JOB_BYTES = 12_000_000
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 64


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("correction child timestamps require explicit UTC")
    return value


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or any(character in value for character in ("\x00", "\n", "\r"))
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
        or value == "."
    ):
        raise ValueError("correction child path must be canonical and relative")
    return value


class G4CorrectionChildDispatchApproval(Contract):
    """Separate creator authority; the cycle admission itself grants no dispatch."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_child_dispatch_approval"] = (
        "g4_correction_child_dispatch_approval"
    )
    dispatch_id: Identifier
    admission_sha256: Digest
    source_revision: SourceRevision
    container_image_id: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    child_signer_id: Identifier
    brief_sha256: Digest
    acceptance_criteria_sha256: Digest
    creator_test_suite_sha256: Digest
    creator_test_bundle_sha256: Digest
    owned_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=MAX_FILES)
    ]
    issued_at: datetime
    expires_at: datetime
    child_dispatch_authorized: Literal[True] = True
    repository_write_authorized: Literal[False] = False
    vcs_write_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("correction child dispatch window is invalid")
        if tuple(_relative_path(path) for path in self.owned_paths) != tuple(
            sorted(set(self.owned_paths))
        ):
            raise ValueError("correction child paths must be unique and sorted")
        return self


class SignedG4CorrectionChildDispatchApproval(Contract):
    approval: G4CorrectionChildDispatchApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_correction_child_dispatch_approval(
    approval: G4CorrectionChildDispatchApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4CorrectionChildDispatchApproval:
    """External creator-signing primitive; no private key enters the dispatcher."""
    return SignedG4CorrectionChildDispatchApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


class G4CorrectionChildSourceFile(Contract):
    path: RelativePath
    content_base64: Annotated[str, Field(max_length=1_333_336)]
    content_sha256: Digest

    @model_validator(mode="after")
    def exact_bytes(self) -> Self:
        _relative_path(self.path)
        try:
            content = base64.b64decode(self.content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("invalid correction child source encoding") from None
        if (
            len(content) > MAX_FILE_BYTES
            or base64.b64encode(content).decode("ascii") != self.content_base64
            or digest(content) != self.content_sha256
        ):
            raise ValueError("correction child source differs from digest")
        return self

    @property
    def content(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class G4CorrectionChildOffer(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_child_offer"] = "g4_correction_child_offer"
    dispatch_approval_sha256: Digest
    correction_admission_sha256: Digest
    source_revision: SourceRevision
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
    max_input_tokens: Annotated[int, Field(ge=1)]
    max_output_tokens: Annotated[int, Field(ge=1)]
    max_tool_calls: Annotated[int, Field(ge=1)]
    max_seconds: Annotated[int, Field(ge=1)]
    max_microusd: Annotated[int, Field(ge=0)]
    provider_dispatch_authorized: Literal[False] = False

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
            raise ValueError("correction child offer paths or size are invalid")
        return self

    @property
    def offer_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4CorrectionChildUsage(Contract):
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    tool_calls: Annotated[int, Field(ge=0)]
    seconds: Annotated[int, Field(ge=0)]
    microusd: Annotated[int, Field(ge=0)]


class G4CorrectionChildProposal(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_child_proposal"] = "g4_correction_child_proposal"
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
            raise ValueError("correction child replacements must be unique and sorted")
        return self


class SignedG4CorrectionChildProposal(Contract):
    proposal: G4CorrectionChildProposal
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_correction_child_proposal(
    proposal: G4CorrectionChildProposal,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4CorrectionChildProposal:
    """External child-signing primitive; the dispatcher never holds this key."""
    return SignedG4CorrectionChildProposal(
        proposal=proposal,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_PROPOSAL_DOMAIN + canonical_bytes(proposal))
            ).decode("ascii"),
        ),
    )


class G4CorrectionChildJob(Contract):
    offer: G4CorrectionChildOffer
    signed_proposal: SignedG4CorrectionChildProposal

    @model_validator(mode="after")
    def exact_offer(self) -> Self:
        if self.signed_proposal.proposal.offer_sha256 != self.offer.offer_sha256:
            raise ValueError("correction child proposal names another offer")
        if len(canonical_bytes(self)) > MAX_JOB_BYTES:
            raise ValueError("correction child job exceeds wire limit")
        return self


class G4CorrectionChildExecution(Contract):
    offer_sha256: Digest
    proposal_sha256: Digest
    changed_paths: Annotated[tuple[RelativePath, ...], Field(min_length=1)]
    replacement_tree_sha256: Digest
    usage: G4CorrectionChildUsage
    unresolved_issue_count: Annotated[int, Field(ge=0)]
    host_repository_modified: Literal[False] = False
    acceptance_authorized: Literal[False] = False


class G4CorrectionChildDispatchReceipt(Contract):
    approval: SignedG4CorrectionChildDispatchApproval
    correction_admission_sha256: Digest
    offer: G4CorrectionChildOffer
    signed_proposal: SignedG4CorrectionChildProposal
    execution: G4CorrectionChildExecution
    dispatched_at: datetime
    repository_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("dispatched_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def exact_links(self) -> Self:
        if (
            self.approval.artifact_sha256 != self.offer.dispatch_approval_sha256
            or self.correction_admission_sha256
            != self.offer.correction_admission_sha256
            or self.signed_proposal.proposal.offer_sha256 != self.offer.offer_sha256
            or self.execution.offer_sha256 != self.offer.offer_sha256
            or self.execution.proposal_sha256 != self.signed_proposal.artifact_sha256
            or len(canonical_bytes(self)) > MAX_JOB_BYTES
        ):
            raise ValueError("correction child receipt links or size are invalid")
        return self


class CorrectionChildGenerator(Protocol):
    """Trusted offline proposal source; this grant permits no live provider call."""

    async def generate(
        self, offer: G4CorrectionChildOffer
    ) -> SignedG4CorrectionChildProposal: ...


def validate_correction_child_job(
    job: G4CorrectionChildJob,
) -> G4CorrectionChildExecution:
    """Pure worker policy, repeated by the host on the returned proposal."""
    offer, proposal = job.offer, job.signed_proposal.proposal
    original = {item.path: item for item in offer.source_files}
    replacements = {item.path: item for item in proposal.replacements}
    if not set(replacements) <= set(original) or all(
        original[path].content_sha256 == item.content_sha256
        for path, item in replacements.items()
    ):
        raise ValueError("correction child made no valid owned-path change")
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
        raise ValueError("correction child exceeded cycle allowance")
    changed = tuple(
        path
        for path, item in replacements.items()
        if item.content_sha256 != original[path].content_sha256
    )
    tree = tuple(
        (path, replacements.get(path, original[path]).content_sha256)
        for path in sorted(original)
    )
    return G4CorrectionChildExecution(
        offer_sha256=offer.offer_sha256,
        proposal_sha256=job.signed_proposal.artifact_sha256,
        changed_paths=changed,
        replacement_tree_sha256=digest(canonical_bytes(_Tree(files=tree))),
        usage=proposal.usage,
        unresolved_issue_count=proposal.unresolved_issue_count,
    )


class _Tree(Contract):
    files: tuple[tuple[str, Digest], ...]


class _CreatorTestBundle(Contract):
    files: tuple[G4CorrectionChildSourceFile, ...]


def creator_test_bundle_sha256(
    files: tuple[G4CorrectionChildSourceFile, ...],
) -> str:
    """Digest the exact creator-test view supplied to this child."""
    return digest(canonical_bytes(_CreatorTestBundle(files=files)))


def _source_file(path: str, content: bytes) -> G4CorrectionChildSourceFile:
    return G4CorrectionChildSourceFile(
        path=path,
        content_base64=base64.b64encode(content).decode("ascii"),
        content_sha256=digest(content),
    )


def _read_repository_file(root: Path, path: str) -> bytes:
    """Read one regular no-link file without following any path component."""
    pieces = _relative_path(path).split("/")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for piece in pieces[:-1]:
            next_fd = os.open(
                piece, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = next_fd
        file_fd = os.open(pieces[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        with os.fdopen(file_fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("creator test is not a unique regular file")
            payload = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(payload) > MAX_FILE_BYTES or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("creator test changed during read or exceeds limit")
        return payload
    finally:
        os.close(fd)


def _claim_name(admission: G4CorrectionCycleAdmission) -> str:
    grant = admission.approval.approval
    return (
        f"{digest(f'{grant.task_id}\x00{grant.cycle}'.encode())}.correction-child-claim"
    )


def _claim(
    store: Path,
    approval: SignedG4CorrectionChildDispatchApproval,
    admission: G4CorrectionCycleAdmission,
) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _claim_name(admission),
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


def _verify_claimed_dispatch(
    store: Path,
    approval: SignedG4CorrectionChildDispatchApproval,
    admission: G4CorrectionCycleAdmission,
) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            _claim_name(admission),
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
                raise ValueError("correction child claim is not private")
            payload = stream.read(MAX_JOB_BYTES + 1)
        if payload != canonical_bytes(approval):
            raise ValueError("correction child claim differs from approval")
    finally:
        os.close(fd)


async def dispatch_correction_child(
    *,
    admission: G4CorrectionCycleAdmission,
    approval: SignedG4CorrectionChildDispatchApproval,
    first: G4CandidateDispatchReceipt,
    provenance: AuthenticatedG4ProvenanceRecord,
    controls: KnownControlValidationRecord,
    binding: ImmutableImplementationBindingRecord,
    package: FrozenReviewerTestPackage,
    reviewer_package_path: Path,
    repository_root: Path,
    implementation_root: Path,
    git_executable: Path,
    candidate_dispatch_store: Path,
    correction_store: Path,
    child_dispatch_store: Path,
    approved_plan: str,
    brief: str,
    acceptance_criteria: str,
    generator: CorrectionChildGenerator,
    container: OfflineContainer,
    now: datetime | None = None,
) -> G4CorrectionChildDispatchReceipt:
    """Spend one separate creator grant and validate one proposal in containment.

    The returned receipt is evidence only. It never applies a patch to the host.
    """
    current = _utc(now if now is not None else datetime.now(UTC))
    root = repository_root.resolve()
    if any(
        path.resolve().is_relative_to(root)
        for path in (
            reviewer_package_path,
            candidate_dispatch_store,
            correction_store,
            child_dispatch_store,
            container.lifecycle_root,
        )
    ):
        raise ValueError("correction child artifacts and stores must be outside Git")
    verify_correction_cycle_claim(correction_store, admission)
    verify_candidate_dispatch_receipt(
        first,
        dispatch_store=candidate_dispatch_store,
        provenance=provenance,
        controls=controls,
        binding=binding,
        package=package,
        reviewer_package_path=reviewer_package_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
    )
    grant = admission.approval.approval
    order = approval.approval
    source = provenance.git_provenance.provenance
    if (
        admission.candidate_receipt_sha256 != first.receipt_sha256
        or admission.provenance_record_sha256 != provenance.record_sha256
        or admission.binding_record_sha256 != binding.binding_record_sha256
        or admission.frozen_reviewer_test_package_sha256
        != package.frozen_package_sha256
        or order.admission_sha256 != admission.admission_sha256
        or order.source_revision != source.source_revision
        or order.source_revision != grant.source_revision
        or order.child_signer_id != grant.child_signer_id
        or digest(approved_plan.encode("utf-8")) != grant.approved_plan_sha256
        or not set(order.owned_paths) <= set(grant.owned_paths)
        or set(order.owned_paths)
        & set(provenance.child_assignment.assignment.creator_test_paths)
        or order.brief_sha256 != digest(brief.encode("utf-8"))
        or order.acceptance_criteria_sha256
        != digest(acceptance_criteria.encode("utf-8"))
        or order.creator_test_suite_sha256 != grant.creator_test_suite_sha256
        or container.image_id != order.container_image_id
        or order.container_image_id != first.admission.request.container_image_id
        or not grant.issued_at <= order.issued_at <= current < order.expires_at
        or order.expires_at > grant.expires_at
        or current >= grant.task_budget.deadline
    ):
        raise ValueError("correction child dispatch differs from approved cycle")
    verify_provenance_signature(
        order, approval.signature, provenance.policy, "creator", _DOMAIN
    )
    sources = snapshot_implementation_files(
        binding.payload.manifest, implementation_root
    )
    if not set(order.owned_paths) <= set(sources):
        raise ValueError("correction child paths must be existing bound source files")
    assignment = provenance.child_assignment.assignment
    if len(assignment.creator_test_paths) > MAX_FILES:
        raise ValueError("correction child creator-test view exceeds file limit")
    creator_tests = tuple(
        _source_file(path, _read_repository_file(root, path))
        for path in assignment.creator_test_paths
    )
    if creator_test_bundle_sha256(creator_tests) != order.creator_test_bundle_sha256:
        raise ValueError("creator test view differs from signed dispatch order")
    offer = G4CorrectionChildOffer(
        dispatch_approval_sha256=approval.artifact_sha256,
        correction_admission_sha256=admission.admission_sha256,
        source_revision=order.source_revision,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        source_files=tuple(
            _source_file(path, sources[path]) for path in order.owned_paths
        ),
        creator_test_files=creator_tests,
        max_input_tokens=grant.max_input_tokens,
        max_output_tokens=grant.max_output_tokens,
        max_tool_calls=grant.max_tool_calls,
        max_seconds=grant.max_seconds,
        max_microusd=grant.max_microusd,
    )
    # A consumed claim is never retried automatically after a crash or model error.
    _claim(child_dispatch_store, approval, admission)
    duration = min(
        float(grant.max_seconds),
        (order.expires_at - current).total_seconds(),
        (grant.task_budget.deadline - current).total_seconds(),
    )
    started = time.monotonic()
    async with asyncio.timeout(duration):
        signed_proposal = await generator.generate(offer)
    verify_provenance_signature(
        signed_proposal.proposal,
        signed_proposal.signature,
        provenance.policy,
        "child",
        _PROPOSAL_DOMAIN,
    )
    if signed_proposal.signature.signer_id != order.child_signer_id:
        raise ValueError("correction proposal came from another child")
    job = G4CorrectionChildJob(offer=offer, signed_proposal=signed_proposal)
    expected = validate_correction_child_job(job)
    remaining = duration - (time.monotonic() - started)
    if remaining <= 0:
        raise TimeoutError("correction child allowance elapsed")
    output = container.execute(
        ("-m", "mos_eisley.run.reviewer_correction_child"),
        canonical_bytes(job),
        timeout=min(remaining, 60.0),
    )
    if len(output) > 16_384:
        raise ValueError("contained correction child result exceeds 16 KB")
    actual = G4CorrectionChildExecution.model_validate_json(output)
    if output != canonical_bytes(actual) or actual != expected:
        raise ValueError("contained correction child result differs from host replay")
    replayed = record_trusted_git_provenance(
        repository_id=source.repository_id,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        binding=binding,
        reviewer_package_path=reviewer_package_path,
        assignment=provenance.child_assignment,
        result=provenance.child_result,
    )
    if replayed != source:
        raise ValueError("correction source changed during child dispatch")
    return G4CorrectionChildDispatchReceipt(
        approval=approval,
        correction_admission_sha256=admission.admission_sha256,
        offer=offer,
        signed_proposal=signed_proposal,
        execution=actual,
        dispatched_at=current,
    )


def verify_correction_child_dispatch_receipt(
    receipt: G4CorrectionChildDispatchReceipt,
    *,
    admission: G4CorrectionCycleAdmission,
    provenance: AuthenticatedG4ProvenanceRecord,
    correction_store: Path,
    child_dispatch_store: Path,
) -> None:
    """Verify durable local claim/links, not provider usage or final acceptance."""
    verify_correction_cycle_claim(correction_store, admission)
    _verify_claimed_dispatch(child_dispatch_store, receipt.approval, admission)
    grant = admission.approval.approval
    order = receipt.approval.approval
    if (
        receipt.correction_admission_sha256 != admission.admission_sha256
        or order.admission_sha256 != admission.admission_sha256
        or order.source_revision != grant.source_revision
        or receipt.offer.source_revision != order.source_revision
        or order.child_signer_id != grant.child_signer_id
        or digest(receipt.offer.approved_plan.encode("utf-8"))
        != grant.approved_plan_sha256
        or not set(order.owned_paths) <= set(grant.owned_paths)
        or tuple(item.path for item in receipt.offer.source_files) != order.owned_paths
        or order.brief_sha256 != digest(receipt.offer.brief.encode("utf-8"))
        or order.acceptance_criteria_sha256
        != digest(receipt.offer.acceptance_criteria.encode("utf-8"))
        or order.creator_test_suite_sha256 != grant.creator_test_suite_sha256
        or creator_test_bundle_sha256(receipt.offer.creator_test_files)
        != order.creator_test_bundle_sha256
        or tuple(item.path for item in receipt.offer.creator_test_files)
        != provenance.child_assignment.assignment.creator_test_paths
        or receipt.offer.max_input_tokens != grant.max_input_tokens
        or receipt.offer.max_output_tokens != grant.max_output_tokens
        or receipt.offer.max_tool_calls != grant.max_tool_calls
        or receipt.offer.max_seconds != grant.max_seconds
        or receipt.offer.max_microusd != grant.max_microusd
        or receipt.dispatched_at >= grant.task_budget.deadline
        or not order.issued_at <= receipt.dispatched_at < order.expires_at
    ):
        raise ValueError("correction child receipt names another cycle or offer")
    verify_provenance_signature(
        receipt.approval.approval,
        receipt.approval.signature,
        provenance.policy,
        "creator",
        _DOMAIN,
    )
    verify_provenance_signature(
        receipt.signed_proposal.proposal,
        receipt.signed_proposal.signature,
        provenance.policy,
        "child",
        _PROPOSAL_DOMAIN,
    )
    if (
        receipt.signed_proposal.signature.signer_id != order.child_signer_id
        or order.source_revision != provenance.git_provenance.provenance.source_revision
    ):
        raise ValueError("correction child receipt signer or source differs")
    if (
        validate_correction_child_job(
            G4CorrectionChildJob(
                offer=receipt.offer, signed_proposal=receipt.signed_proposal
            )
        )
        != receipt.execution
    ):
        raise ValueError("correction child execution differs from replay")
