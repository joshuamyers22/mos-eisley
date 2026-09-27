"""One-use, separately authorized Git integration of a real G4 initial child."""

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
from mos_eisley.reviewer_correction_dispatch import _read_repository_file
from mos_eisley.reviewer_correction_integration import (
    MAX_PATCH_BYTES,
    _preflight_tree,
    _write_existing_file,
)
from mos_eisley.reviewer_initial_child import (
    G4InitialChildDispatchReceipt,
    verify_initial_child_dispatch_receipt,
)
from mos_eisley.reviewer_initial_coding_broker import (
    G4ProductionInitialChildReceipt,
    verify_production_initial_child_receipt,
)
from mos_eisley.reviewer_provenance import (
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
from mos_eisley.run.spend_ledger import SpendLedger

_APPROVAL_DOMAIN = b"mos-eisley/g4-initial-integration-approval/v1\x00"
_RECORD_DOMAIN = b"mos-eisley/g4-initial-integration-record/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("initial integration requires explicit UTC timestamps")
    return value


class G4InitialIntegrationApproval(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_integration_approval"] = "g4_initial_integration_approval"
    integration_id: Identifier
    policy_sha256: Digest
    assignment_sha256: Digest
    child_dispatch_receipt_sha256: Digest
    production_receipt_sha256: Digest
    source_revision: SourceRevision
    target_root_sha256: Digest
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
            raise ValueError("initial integration window is invalid")
        if self.owned_paths != tuple(sorted(set(self.owned_paths))):
            raise ValueError("initial integration paths must be sorted and unique")
        return self


class SignedG4InitialIntegrationApproval(Contract):
    approval: G4InitialIntegrationApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_initial_integration_approval(
    approval: G4InitialIntegrationApproval, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4InitialIntegrationApproval:
    return SignedG4InitialIntegrationApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_APPROVAL_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


class G4InitialIntegrationRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_integration_record"] = "g4_initial_integration_record"
    approval: SignedG4InitialIntegrationApproval
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
            self.approval.approval.child_dispatch_receipt_sha256
            != self.child_dispatch_receipt_sha256
            or self.approval.approval.source_revision != self.source_revision
            or self.source_revision == self.integrated_revision
            or self.changed_paths != self.approval.approval.owned_paths
            or len(canonical_bytes(self)) > 16_384
        ):
            raise ValueError("initial integration record links differ")
        return self

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SignedG4InitialIntegrationRecord(Contract):
    record: G4InitialIntegrationRecord
    signature: G4ArtifactSignature


def sign_initial_integration_record(
    record: G4InitialIntegrationRecord, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4InitialIntegrationRecord:
    return SignedG4InitialIntegrationRecord(
        record=record,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_RECORD_DOMAIN + canonical_bytes(record))
            ).decode("ascii"),
        ),
    )


def _worktree_name(approval: G4InitialIntegrationApproval) -> str:
    return "g4-initial-" + digest(approval.integration_id.encode())[:24]


def _check_inputs(
    *,
    signed: SignedG4InitialIntegrationApproval,
    dispatch: G4InitialChildDispatchReceipt,
    production: G4ProductionInitialChildReceipt,
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
    production_store: Path,
    ledger: SpendLedger,
    integration_store: Path,
    now: datetime,
) -> tuple[Path, Path, str]:
    root = repository_root.resolve(strict=True)
    store_fd = open_private_dispatch_store(integration_store)
    os.close(store_fd)
    store = integration_store.resolve(strict=True)
    if (
        not repository_root.is_absolute()
        or repository_root.is_symlink()
        or store.is_relative_to(root)
        or root.is_relative_to(store)
        or any(
            path.resolve().is_relative_to(root)
            for path in (dispatch_store, production_store, integration_store)
        )
    ):
        raise ValueError("initial integration state overlaps source repository")
    verify_initial_child_dispatch_receipt(
        dispatch,
        policy=policy,
        creator=creator,
        custody=custody,
        assignment=assignment,
        package=package,
        repository_root=root,
        git_executable=git_executable,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        container=container,
        dispatch_store=dispatch_store,
    )
    verify_production_initial_child_receipt(
        production, dispatch, policy, ledger, production_store
    )
    order = signed.approval
    verify_provenance_signature(
        order, signed.signature, policy, "creator", _APPROVAL_DOMAIN
    )
    if (
        order.policy_sha256 != policy.policy_sha256
        or order.assignment_sha256 != assignment.artifact_sha256
        or order.child_dispatch_receipt_sha256 != dispatch.receipt_sha256
        or order.production_receipt_sha256 != production.receipt_sha256
        or order.source_revision != assignment.assignment.base_revision
        or order.target_root_sha256 != digest(str(root).encode())
        or order.integration_store_sha256 != digest(str(store).encode())
        or order.owned_paths != dispatch.execution.changed_paths
        or dispatch.execution.unresolved_issue_count != 0
        or not dispatch.dispatched_at <= order.issued_at <= now < order.expires_at
        or not policy.valid_from <= order.issued_at < policy.valid_until
        or order.expires_at > policy.valid_until
    ):
        raise ValueError("initial integration differs from signed child or custody")
    if _git_text(git_executable, root, ["rev-parse", "HEAD"]) != order.source_revision:
        raise ValueError("initial integration base HEAD changed")
    if _git(
        git_executable,
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ):
        raise ValueError("initial integration source checkout is dirty")
    _preflight_tree(git_executable, root, order.source_revision)
    return root, store, _worktree_name(order)


def _claim(store: Path, name: str, signed: SignedG4InitialIntegrationApproval) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            name + ".claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(signed))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_claim(
    store: Path, name: str, signed: SignedG4InitialIntegrationApproval
) -> None:
    fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(name + ".claim", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or stream.read(16_385) != canonical_bytes(signed)
            ):
                raise ValueError("initial integration claim differs or is not private")
    finally:
        os.close(fd)


def _verify_git(
    *,
    git: Path,
    root: Path,
    worktree: Path,
    source: str,
    dispatch: G4InitialChildDispatchReceipt,
) -> tuple[str, str, bytes]:
    original_common = Path(_git_text(git, root, ["rev-parse", "--git-common-dir"]))
    worktree_common = Path(_git_text(git, worktree, ["rev-parse", "--git-common-dir"]))
    if not original_common.is_absolute():
        original_common = root / original_common
    if not worktree_common.is_absolute():
        worktree_common = worktree / worktree_common
    if (
        original_common.resolve() != worktree_common.resolve()
        or Path(_git_text(git, root, ["rev-parse", "--show-toplevel"])).resolve()
        != root
        or Path(_git_text(git, worktree, ["rev-parse", "--show-toplevel"])).resolve()
        != worktree
        or _git_text(git, worktree, ["rev-parse", "HEAD^1"]) != source
        or _git_text(git, root, ["rev-parse", "HEAD"]) != source
        or _git(git, root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        or _git(
            git, worktree, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
        )
    ):
        raise ValueError("initial integration Git worktrees or lineage differ")
    integrated = _git_text(git, worktree, ["rev-parse", "HEAD"])
    if (
        _git_text(git, worktree, ["rev-list", "--parents", "-n", "1", "HEAD"])
        != f"{integrated} {source}"
    ):
        raise ValueError("initial integration commit has another parent")
    names = tuple(
        sorted(
            path.decode()
            for path in _git(
                git,
                worktree,
                ["diff", "--name-only", "-z", "--no-renames", source, integrated],
            ).split(b"\x00")
            if path
        )
    )
    if names != dispatch.execution.changed_paths:
        raise ValueError("initial integration changed paths outside child proposal")
    replacements = {
        item.path: item.content
        for item in dispatch.signed_proposal.proposal.replacements
    }
    for path in names:
        if (
            _read_repository_file(worktree, path) != replacements[path]
            or _git(git, worktree, ["show", f"{integrated}:{path}"], limit=1_000_001)
            != replacements[path]
        ):
            raise ValueError("initial integration bytes differ from signed proposal")
    patch = _git(
        git,
        worktree,
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            source,
            integrated,
            "--",
        ],
        limit=MAX_PATCH_BYTES,
    )
    if not patch:
        raise ValueError("initial integration produced an empty patch")
    tree = _git_text(git, worktree, ["rev-parse", f"{integrated}^{{tree}}"])
    return integrated, tree, patch


def integrate_initial_child(
    *,
    signed: SignedG4InitialIntegrationApproval,
    dispatch: G4InitialChildDispatchReceipt,
    production: G4ProductionInitialChildReceipt,
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
    production_store: Path,
    ledger: SpendLedger,
    integration_store: Path,
    now: datetime | None = None,
) -> G4InitialIntegrationRecord:
    current = _utc(now if now is not None else datetime.now(UTC))
    root, store, name = _check_inputs(
        signed=signed,
        dispatch=dispatch,
        production=production,
        policy=policy,
        creator=creator,
        custody=custody,
        assignment=assignment,
        package=package,
        repository_root=repository_root,
        git_executable=git_executable,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        container=container,
        dispatch_store=dispatch_store,
        production_store=production_store,
        ledger=ledger,
        integration_store=integration_store,
        now=current,
    )
    worktree = store / name
    if worktree.exists() or worktree.is_symlink():
        raise ValueError("initial integration worktree already exists")
    _claim(store, name, signed)
    source = signed.approval.source_revision
    _git(
        git_executable,
        root,
        [
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.sparseCheckout=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.attributesFile=/dev/null",
            "worktree",
            "add",
            "--detach",
            str(worktree),
            source,
        ],
        limit=4096,
    )
    if (
        worktree.resolve(strict=True) != worktree
        or _git_text(git_executable, worktree, ["rev-parse", "HEAD"]) != source
    ):
        raise ValueError("initial integration worktree checkout differs")
    originals = {item.path: item.content for item in dispatch.offer.source_files}
    replacements = {
        item.path: item.content
        for item in dispatch.signed_proposal.proposal.replacements
    }
    for path in dispatch.execution.changed_paths:
        _write_existing_file(worktree, path, originals[path], replacements[path])
    _git(
        git_executable,
        worktree,
        ["-c", "core.autocrlf=false", "add", "--", *dispatch.execution.changed_paths],
        limit=4096,
    )
    staged = tuple(
        sorted(
            path.decode()
            for path in _git(
                git_executable, worktree, ["diff", "--cached", "--name-only", "-z"]
            ).split(b"\x00")
            if path
        )
    )
    if staged != dispatch.execution.changed_paths:
        raise ValueError("initial integration staged unexpected paths")
    _git(
        git_executable,
        worktree,
        [
            "-c",
            "user.name=Mos Eisley",
            "-c",
            "user.email=mos-eisley@localhost",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-m",
            f"G4 initial child {signed.approval.integration_id}",
        ],
        limit=4096,
    )
    integrated, tree, patch = _verify_git(
        git=git_executable,
        root=root,
        worktree=worktree,
        source=source,
        dispatch=dispatch,
    )
    return G4InitialIntegrationRecord(
        approval=signed,
        child_dispatch_receipt_sha256=dispatch.receipt_sha256,
        source_revision=source,
        integrated_revision=integrated,
        integrated_tree_id=tree,
        patch_sha256=digest(patch),
        patch_bytes=len(patch),
        changed_paths=dispatch.execution.changed_paths,
        worktree_name=name,
        integrated_at=current,
    )


def verify_initial_integration_record(
    signed_record: SignedG4InitialIntegrationRecord,
    *,
    dispatch: G4InitialChildDispatchReceipt,
    production: G4ProductionInitialChildReceipt,
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
    production_store: Path,
    ledger: SpendLedger,
    integration_store: Path,
) -> None:
    record = signed_record.record
    verify_provenance_signature(
        record, signed_record.signature, policy, "vcs", _RECORD_DOMAIN
    )
    root, store, name = _check_inputs(
        signed=record.approval,
        dispatch=dispatch,
        production=production,
        policy=policy,
        creator=creator,
        custody=custody,
        assignment=assignment,
        package=package,
        repository_root=repository_root,
        git_executable=git_executable,
        approved_plan=approved_plan,
        brief=brief,
        acceptance_criteria=acceptance_criteria,
        container=container,
        dispatch_store=dispatch_store,
        production_store=production_store,
        ledger=ledger,
        integration_store=integration_store,
        now=record.integrated_at,
    )
    if record.worktree_name != name:
        raise ValueError("initial integration worktree name differs")
    _verify_claim(store, name, record.approval)
    worktree = store / name
    if not worktree.is_dir() or worktree.resolve(strict=True) != worktree:
        raise ValueError("initial integration worktree moved")
    integrated, tree, patch = _verify_git(
        git=git_executable,
        root=root,
        worktree=worktree,
        source=record.source_revision,
        dispatch=dispatch,
    )
    if (
        integrated != record.integrated_revision
        or tree != record.integrated_tree_id
        or digest(patch) != record.patch_sha256
        or len(patch) != record.patch_bytes
        or record.changed_paths != dispatch.execution.changed_paths
    ):
        raise ValueError("initial integration record differs from Git")
