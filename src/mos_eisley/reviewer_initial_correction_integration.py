"""Separate write authority for an initial-child correction proposal.

Signing and previewing this grant perform no Git write or task test. A later
one-use integration broker must consume the grant before making a detached
commit and independently verify its resulting Git record.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_coding_broker import (
    G4ProductionCodingChildReceipt,
    verify_production_coding_child_receipt,
)
from mos_eisley.reviewer_correction import G4CorrectionReviewPolicy
from mos_eisley.reviewer_correction_dispatch import G4CorrectionChildDispatchReceipt
from mos_eisley.reviewer_correction_integration import (
    MAX_PATCH_BYTES,
    _preflight_tree,
    _verify_integrated_git,
    _write_existing_file,
)
from mos_eisley.reviewer_initial_candidate import (
    G4InitialCandidateInputs,
    G4InitialCandidateReceipt,
)
from mos_eisley.reviewer_initial_correction import G4InitialCorrectionCycleAdmission
from mos_eisley.reviewer_initial_correction_dispatch import (
    verify_initial_correction_child_dispatch_receipt,
)
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    RelativePath,
    SourceRevision,
    _git,
    _git_text,
    verify_provenance_signature,
)

_APPROVAL_DOMAIN = b"mos-eisley/g4-initial-correction-integration-approval/v1\x00"
_RECORD_DOMAIN = b"mos-eisley/g4-initial-correction-integration-record/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("initial correction integration needs explicit UTC")
    return value


class G4InitialCorrectionIntegrationApproval(Contract):
    """Exact creator authority to write one detached correction worktree."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_correction_integration_approval"] = (
        "g4_initial_correction_integration_approval"
    )
    integration_id: Identifier
    policy_sha256: Digest
    admission_sha256: Digest
    child_dispatch_receipt_sha256: Digest
    production_receipt_sha256: Digest
    source_revision: SourceRevision
    source_root_sha256: Digest
    integration_store_sha256: Digest
    owned_paths: Annotated[tuple[RelativePath, ...], Field(min_length=1, max_length=64)]
    issued_at: datetime
    expires_at: datetime
    isolated_worktree_write_authorized: Literal[True] = True
    checked_out_worktree_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    final_test_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("initial correction integration window is invalid")
        if self.owned_paths != tuple(sorted(set(self.owned_paths))):
            raise ValueError("initial correction integration paths must be unique")
        return self


class SignedG4InitialCorrectionIntegrationApproval(Contract):
    approval: G4InitialCorrectionIntegrationApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4InitialCorrectionIntegrationRecord(Contract):
    """Exact isolated commit evidence, awaiting a separate VCS signature."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_correction_integration_record"] = (
        "g4_initial_correction_integration_record"
    )
    approval: SignedG4InitialCorrectionIntegrationApproval
    child_dispatch_receipt_sha256: Digest
    source_revision: SourceRevision
    integrated_revision: SourceRevision
    integrated_tree_id: SourceRevision
    patch_sha256: Digest
    patch_bytes: Annotated[int, Field(ge=1, le=MAX_PATCH_BYTES)]
    changed_paths: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=64)
    ]
    worktree_name: Identifier
    integrated_at: datetime
    original_head_unchanged: Literal[True] = True
    isolated_worktree_clean: Literal[True] = True
    final_tests_passed: Literal[False] = False
    independent_review_passed: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("integrated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def exact_links(self) -> Self:
        if (
            self.child_dispatch_receipt_sha256
            != self.approval.approval.child_dispatch_receipt_sha256
            or self.source_revision != self.approval.approval.source_revision
            or self.integrated_revision == self.source_revision
            or self.changed_paths != self.approval.approval.owned_paths
            or not self.approval.approval.issued_at
            <= self.integrated_at
            < self.approval.approval.expires_at
            or len(canonical_bytes(self)) > 16_384
        ):
            raise ValueError("initial correction integration record links differ")
        return self

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SignedG4InitialCorrectionIntegrationRecord(Contract):
    record: G4InitialCorrectionIntegrationRecord
    signature: G4ArtifactSignature


def sign_initial_correction_integration_record(
    record: G4InitialCorrectionIntegrationRecord,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4InitialCorrectionIntegrationRecord:
    """Attest the replayable Git result with an enrolled VCS key."""
    return SignedG4InitialCorrectionIntegrationRecord(
        record=record,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_RECORD_DOMAIN + canonical_bytes(record))
            ).decode("ascii"),
        ),
    )


def sign_initial_correction_integration_approval(
    approval: G4InitialCorrectionIntegrationApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4InitialCorrectionIntegrationApproval:
    """Sign externally; the private creator key never enters the verifier."""
    return SignedG4InitialCorrectionIntegrationApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_APPROVAL_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


def verify_initial_correction_integration_approval(
    signed: SignedG4InitialCorrectionIntegrationApproval,
    *,
    admission: G4InitialCorrectionCycleAdmission,
    dispatch: G4CorrectionChildDispatchReceipt,
    production: G4ProductionCodingChildReceipt,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    child_dispatch_store: Path,
    production_store: Path,
    integration_store: Path,
    now: datetime | None = None,
) -> None:
    """Replay exact authority and current clean source without spending it."""
    current = _utc(now if now is not None else datetime.now(UTC))
    source_root = first_inputs.integrated_root.resolve(strict=True)
    original_root = first_inputs.original_root.resolve(strict=True)
    fd = open_private_dispatch_store(integration_store)
    try:
        store = integration_store.resolve(strict=True)
    finally:
        os.close(fd)
    if (
        first_inputs.integrated_root.is_symlink()
        or first_inputs.original_root.is_symlink()
        or source_root == original_root
        or any(
            path.resolve().is_relative_to(root)
            for root in (source_root, original_root)
            for path in (
                correction_store,
                child_dispatch_store,
                production_store,
                store,
            )
        )
        or source_root.is_relative_to(store)
        or original_root.is_relative_to(store)
    ):
        raise ValueError("initial correction integration state overlaps Git")
    verify_initial_correction_child_dispatch_receipt(
        dispatch,
        admission=admission,
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        review_policy=review_policy,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
        container=first_inputs.container,
    )
    verify_production_coding_child_receipt(
        production, dispatch, first_inputs.policy, first_inputs.ledger, production_store
    )
    order = signed.approval
    cycle = admission.approval.approval
    if (
        order.policy_sha256 != first_inputs.policy.policy_sha256
        or order.admission_sha256 != admission.admission_sha256
        or order.child_dispatch_receipt_sha256 != digest(canonical_bytes(dispatch))
        or order.production_receipt_sha256 != production.receipt_sha256
        or order.source_revision != admission.source_revision
        or order.source_root_sha256 != digest(str(source_root).encode("utf-8"))
        or order.integration_store_sha256 != digest(str(store).encode("utf-8"))
        or order.owned_paths != dispatch.execution.changed_paths
        or dispatch.execution.unresolved_issue_count != 0
        or not dispatch.dispatched_at <= order.issued_at <= current < order.expires_at
        or order.expires_at > cycle.expires_at
        or order.expires_at > cycle.task_budget.deadline
        or order.expires_at > first_inputs.policy.valid_until
        or order.issued_at < first_inputs.policy.valid_from
    ):
        raise ValueError("initial correction integration differs from signed task")
    verify_provenance_signature(
        order,
        signed.signature,
        first_inputs.policy,
        "creator",
        _APPROVAL_DOMAIN,
    )
    if _git_text(first_inputs.git_executable, source_root, ["rev-parse", "HEAD"]) != (
        order.source_revision
    ) or _git(
        first_inputs.git_executable,
        source_root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ):
        raise ValueError("initial correction integration source Git changed")
    _preflight_tree(first_inputs.git_executable, source_root, order.source_revision)


def _worktree_name(order: G4InitialCorrectionIntegrationApproval) -> str:
    return "g4-initial-correction-" + digest(order.integration_id.encode())[:24]


def _claim(
    store: Path, name: str, signed: SignedG4InitialCorrectionIntegrationApproval
) -> None:
    directory_fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            name + ".claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(signed))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _verify_claim(
    store: Path, name: str, signed: SignedG4InitialCorrectionIntegrationApproval
) -> None:
    directory_fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            name + ".claim", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd
        )
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or stream.read(16_385) != canonical_bytes(signed)
            ):
                raise ValueError("initial correction integration claim differs")
    finally:
        os.close(directory_fd)


def _verify_git(
    git: Path,
    root: Path,
    worktree: Path,
    source: str,
    dispatch: G4CorrectionChildDispatchReceipt,
) -> tuple[str, str, bytes]:
    if not worktree.is_dir() or worktree.resolve(strict=True) != worktree:
        raise ValueError("initial correction worktree moved")
    integrated, tree, patch = _verify_integrated_git(
        git=git, root=root, worktree=worktree, source=source, receipt=dispatch
    )
    if _git_text(git, worktree, ["rev-list", "--parents", "-n", "1", "HEAD"]) != (
        f"{integrated} {source}"
    ):
        raise ValueError("initial correction integration has another parent")
    return integrated, tree, patch


def integrate_initial_correction_child(
    *,
    signed: SignedG4InitialCorrectionIntegrationApproval,
    admission: G4InitialCorrectionCycleAdmission,
    dispatch: G4CorrectionChildDispatchReceipt,
    production: G4ProductionCodingChildReceipt,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    child_dispatch_store: Path,
    production_store: Path,
    integration_store: Path,
) -> G4InitialCorrectionIntegrationRecord:
    """Consume one owner grant, writing only a new detached worktree."""
    verify_initial_correction_integration_approval(
        signed,
        admission=admission,
        dispatch=dispatch,
        production=production,
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        review_policy=review_policy,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
        production_store=production_store,
        integration_store=integration_store,
    )
    order = signed.approval
    root = first_inputs.integrated_root.resolve(strict=True)
    store = integration_store.resolve(strict=True)
    name = _worktree_name(order)
    worktree = store / name
    if worktree.exists() or worktree.is_symlink():
        raise ValueError("initial correction integration worktree already exists")
    _claim(store, name, signed)
    git = first_inputs.git_executable
    _git(
        git,
        root,
        [
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.sparseCheckout=false",
            "worktree",
            "add",
            "--detach",
            str(worktree),
            order.source_revision,
        ],
        limit=4096,
    )
    if (
        worktree.resolve(strict=True) != worktree
        or _git_text(git, worktree, ["rev-parse", "HEAD"]) != order.source_revision
        or _git(
            git, worktree, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
        )
    ):
        raise ValueError("initial correction worktree checkout differs")
    originals = {item.path: item.content for item in dispatch.offer.source_files}
    replacements = {
        item.path: item.content
        for item in dispatch.signed_proposal.proposal.replacements
    }
    for path in order.owned_paths:
        _write_existing_file(worktree, path, originals[path], replacements[path])
    _git(git, worktree, ["-c", "core.autocrlf=false", "add", "--", *order.owned_paths])
    staged = tuple(
        sorted(
            path.decode("utf-8")
            for path in _git(
                git, worktree, ["diff", "--cached", "--name-only", "-z"]
            ).split(b"\x00")
            if path
        )
    )
    if staged != order.owned_paths:
        raise ValueError("initial correction integration staged unexpected paths")
    _git(
        git,
        worktree,
        [
            "-c",
            "user.name=Mos Eisley",
            "-c",
            "user.email=mos-eisley@localhost",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            f"G4 initial correction {order.integration_id}",
        ],
        limit=4096,
    )
    integrated, tree, patch = _verify_git(
        git, root, worktree, order.source_revision, dispatch
    )
    completed_at = datetime.now(UTC)
    if completed_at >= order.expires_at:
        raise ValueError("initial correction grant expired before Git verification")
    return G4InitialCorrectionIntegrationRecord(
        approval=signed,
        child_dispatch_receipt_sha256=order.child_dispatch_receipt_sha256,
        source_revision=order.source_revision,
        integrated_revision=integrated,
        integrated_tree_id=tree,
        patch_sha256=digest(patch),
        patch_bytes=len(patch),
        changed_paths=order.owned_paths,
        worktree_name=name,
        integrated_at=completed_at,
    )


def verify_initial_correction_integration_record(
    signed_record: SignedG4InitialCorrectionIntegrationRecord,
    *,
    admission: G4InitialCorrectionCycleAdmission,
    dispatch: G4CorrectionChildDispatchReceipt,
    production: G4ProductionCodingChildReceipt,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    child_dispatch_store: Path,
    production_store: Path,
    integration_store: Path,
) -> None:
    """Replay the signed VCS attestation against exact current Git bytes."""
    record = signed_record.record
    verify_provenance_signature(
        record, signed_record.signature, first_inputs.policy, "vcs", _RECORD_DOMAIN
    )
    verify_initial_correction_integration_approval(
        record.approval,
        admission=admission,
        dispatch=dispatch,
        production=production,
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        review_policy=review_policy,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
        production_store=production_store,
        integration_store=integration_store,
        now=record.integrated_at,
    )
    order = record.approval.approval
    name = _worktree_name(order)
    if record.worktree_name != name:
        raise ValueError("initial correction worktree name differs")
    store = integration_store.resolve(strict=True)
    _verify_claim(store, name, record.approval)
    integrated, tree, patch = _verify_git(
        first_inputs.git_executable,
        first_inputs.integrated_root.resolve(strict=True),
        store / name,
        record.source_revision,
        dispatch,
    )
    if (
        integrated != record.integrated_revision
        or tree != record.integrated_tree_id
        or digest(patch) != record.patch_sha256
        or len(patch) != record.patch_bytes
    ):
        raise ValueError("initial correction integration record differs from Git")
