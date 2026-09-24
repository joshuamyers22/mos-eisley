"""One-use offline Git integration of a signed G4 correction proposal.

Only a fresh, private, detached worktree may be changed. The caller's checkout
is replayed read-only; a separate creator grant is required for the write.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import os
import stat
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import (
    G4CandidateDispatchReceipt,
    open_private_dispatch_store,
    verify_candidate_dispatch_receipt,
)
from mos_eisley.reviewer_correction import G4CorrectionCycleAdmission
from mos_eisley.reviewer_correction_dispatch import (
    G4CorrectionChildDispatchReceipt,
    _read_repository_file,
    verify_correction_child_dispatch_receipt,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
)
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    RelativePath,
    SourceRevision,
    _git,
    _git_text,
    _parse_ls_tree,
    _relative_path,
    record_trusted_git_provenance,
    verify_provenance_signature,
)
from mos_eisley.reviewer_test_execution import KnownControlValidationRecord
from mos_eisley.reviewer_test_package import FrozenReviewerTestPackage

_APPROVAL_DOMAIN = b"mos-eisley/g4-correction-integration-approval/v1\x00"
_RECORD_DOMAIN = b"mos-eisley/g4-correction-integration-record/v1\x00"
MAX_TREE_FILES = 2048
MAX_TREE_BYTES = 32_000_000
MAX_PATCH_BYTES = 8_000_000


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("correction integration timestamps require explicit UTC")
    return value


class G4CorrectionIntegrationApproval(Contract):
    """Separate creator authority for one exact worktree-only Git integration."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_integration_approval"] = (
        "g4_correction_integration_approval"
    )
    integration_id: Identifier
    policy_sha256: Digest
    admission_sha256: Digest
    child_dispatch_receipt_sha256: Digest
    repository_id: Identifier
    source_revision: SourceRevision
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
            raise ValueError("correction integration window is invalid")
        if tuple(_relative_path(path) for path in self.owned_paths) != tuple(
            sorted(set(self.owned_paths))
        ):
            raise ValueError("correction integration paths must be sorted and unique")
        return self


class SignedG4CorrectionIntegrationApproval(Contract):
    approval: G4CorrectionIntegrationApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_correction_integration_approval(
    approval: G4CorrectionIntegrationApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4CorrectionIntegrationApproval:
    return SignedG4CorrectionIntegrationApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_APPROVAL_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


class G4CorrectionIntegrationRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_correction_integration_record"] = (
        "g4_correction_integration_record"
    )
    approval: SignedG4CorrectionIntegrationApproval
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
            raise ValueError("correction integration record links are invalid")
        return self

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SignedG4CorrectionIntegrationRecord(Contract):
    record: G4CorrectionIntegrationRecord
    signature: G4ArtifactSignature


def sign_correction_integration_record(
    record: G4CorrectionIntegrationRecord,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4CorrectionIntegrationRecord:
    """External VCS signer attests the replayable integration record."""
    return SignedG4CorrectionIntegrationRecord(
        record=record,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_RECORD_DOMAIN + canonical_bytes(record))
            ).decode("ascii"),
        ),
    )


def _worktree_name(admission: G4CorrectionCycleAdmission) -> str:
    grant = admission.approval.approval
    return f"g4-{digest(f'{grant.task_id}\x00{grant.cycle}'.encode())[:32]}"


def _claim(
    store: Path, name: str, approval: SignedG4CorrectionIntegrationApproval
) -> None:
    directory_fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            f"{name}.claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(claim_fd, "wb") as stream:
            stream.write(canonical_bytes(approval))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _verify_claim(
    store: Path, name: str, approval: SignedG4CorrectionIntegrationApproval
) -> None:
    directory_fd = open_private_dispatch_store(store)
    try:
        claim_fd = os.open(
            f"{name}.claim", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd
        )
        with os.fdopen(claim_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise ValueError("correction integration claim is not private")
            payload = stream.read(16_385)
        if payload != canonical_bytes(approval):
            raise ValueError("correction integration claim differs from approval")
    finally:
        os.close(directory_fd)


def _preflight_tree(git: Path, root: Path, revision: str) -> None:
    """Bound checkout size and deny Git tree features that can execute filters."""
    entries = _parse_ls_tree(_git(git, root, ["ls-tree", "-r", "-z", revision]))
    if not entries or len(entries) > MAX_TREE_FILES:
        raise ValueError("correction integration tree file count is unsafe")
    folded: set[str] = set()
    total = 0
    for path, (mode, kind, object_id) in entries.items():
        pieces = path.split("/")
        folded_path = unicodedata.normalize("NFD", path).casefold()
        if (
            mode not in {"100644", "100755"}
            or kind != "blob"
            or any(
                piece.casefold() in {".git", ".gitattributes", ".gitmodules"}
                or piece.endswith((" ", "."))
                for piece in pieces
            )
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
            or folded_path in folded
        ):
            raise ValueError("correction integration tree contains unsafe Git material")
        folded.add(folded_path)
        size_text = _git_text(git, root, ["cat-file", "-s", object_id])
        if not size_text.isdecimal():
            raise ValueError("Git returned invalid blob size")
        total += int(size_text)
        if total > MAX_TREE_BYTES:
            raise ValueError("correction integration tree exceeds byte limit")
    info_attributes = Path(
        _git_text(git, root, ["rev-parse", "--git-path", "info/attributes"])
    )
    if not info_attributes.is_absolute():
        info_attributes = root / info_attributes
    if info_attributes.exists() or info_attributes.is_symlink():
        attr = info_attributes.lstat()
        if not stat.S_ISREG(attr.st_mode) or attr.st_size != 0:
            raise ValueError("Git info attributes could alter worktree checkout")


def _write_existing_file(root: Path, path: str, before: bytes, after: bytes) -> None:
    """Replace only an existing unique regular file through no-follow dirfds."""
    pieces = _relative_path(path).split("/")
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for piece in pieces[:-1]:
            child_fd = os.open(
                piece, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd
            )
            os.close(directory_fd)
            directory_fd = child_fd
        file_fd = os.open(pieces[-1], os.O_RDWR | os.O_NOFOLLOW, dir_fd=directory_fd)
        with os.fdopen(file_fd, "r+b") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError(
                    "correction integration target is not a unique regular file"
                )
            if stream.read(len(before) + 1) != before:
                raise ValueError(
                    "correction integration target differs from signed source"
                )
            stream.seek(0)
            stream.truncate(0)
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(directory_fd)


def _check_original_inputs(
    *,
    admission: G4CorrectionCycleAdmission,
    receipt: G4CorrectionChildDispatchReceipt,
    approval: SignedG4CorrectionIntegrationApproval,
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
    integration_store: Path,
    now: datetime,
) -> tuple[Path, Path, str]:
    root = repository_root.resolve(strict=True)
    store_fd = open_private_dispatch_store(integration_store)
    os.close(store_fd)
    store = integration_store.resolve(strict=True)
    if any(
        path.resolve().is_relative_to(root)
        for path in (
            reviewer_package_path,
            candidate_dispatch_store,
            correction_store,
            child_dispatch_store,
            integration_store,
        )
    ) or root.is_relative_to(store):
        raise ValueError("correction integration state must be outside the repository")
    verify_candidate_dispatch_receipt(
        first,
        dispatch_store=candidate_dispatch_store,
        provenance=provenance,
        controls=controls,
        binding=binding,
        package=package,
        reviewer_package_path=reviewer_package_path,
        repository_root=root,
        implementation_root=implementation_root,
        git_executable=git_executable,
    )
    verify_correction_child_dispatch_receipt(
        receipt,
        admission=admission,
        provenance=provenance,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
    )
    source = provenance.git_provenance.provenance
    grant = admission.approval.approval
    order = approval.approval
    if (
        admission.candidate_receipt_sha256 != first.receipt_sha256
        or order.policy_sha256 != provenance.policy.policy_sha256
        or order.admission_sha256 != admission.admission_sha256
        or order.child_dispatch_receipt_sha256 != digest(canonical_bytes(receipt))
        or order.repository_id != source.repository_id
        or order.source_revision != source.source_revision
        or order.owned_paths != receipt.execution.changed_paths
        or not set(order.owned_paths) <= set(grant.owned_paths)
        or not receipt.dispatched_at <= order.issued_at <= now < order.expires_at
        or order.expires_at > grant.expires_at
        or now >= grant.task_budget.deadline
    ):
        raise ValueError("correction integration differs from signed cycle or proposal")
    verify_provenance_signature(
        order, approval.signature, provenance.policy, "creator", _APPROVAL_DOMAIN
    )
    replayed = record_trusted_git_provenance(
        repository_id=source.repository_id,
        repository_root=root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        binding=binding,
        reviewer_package_path=reviewer_package_path,
        assignment=provenance.child_assignment,
        result=provenance.child_result,
    )
    if replayed != source:
        raise ValueError("correction integration source provenance changed")
    for test in receipt.offer.creator_test_files:
        if _read_repository_file(root, test.path) != test.content:
            raise ValueError("creator test changed before correction integration")
    if _git(
        git_executable,
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ):
        raise ValueError("correction integration requires a clean original checkout")
    if (
        _git_text(git_executable, root, ["rev-parse", "--verify", "HEAD^{commit}"])
        != source.source_revision
    ):
        raise ValueError("correction integration source HEAD changed")
    _preflight_tree(git_executable, root, source.source_revision)
    return root, store, _worktree_name(admission)


def _verify_integrated_git(
    *,
    git: Path,
    root: Path,
    worktree: Path,
    source: str,
    receipt: G4CorrectionChildDispatchReceipt,
) -> tuple[str, str, bytes]:
    original_top = Path(
        _git_text(git, root, ["rev-parse", "--show-toplevel"])
    ).resolve()
    worktree_top = Path(
        _git_text(git, worktree, ["rev-parse", "--show-toplevel"])
    ).resolve()
    original_common = Path(_git_text(git, root, ["rev-parse", "--git-common-dir"]))
    worktree_common = Path(_git_text(git, worktree, ["rev-parse", "--git-common-dir"]))
    if not original_common.is_absolute():
        original_common = root / original_common
    if not worktree_common.is_absolute():
        worktree_common = worktree / worktree_common
    if (
        original_top != root
        or worktree_top != worktree
        or original_common.resolve() != worktree_common.resolve()
    ):
        raise ValueError(
            "correction integration worktree belongs to another repository"
        )
    integrated = _git_text(git, worktree, ["rev-parse", "--verify", "HEAD^{commit}"])
    if _git_text(git, worktree, ["rev-parse", "--verify", "HEAD^1^{commit}"]) != source:
        raise ValueError("correction integration commit has another parent")
    if _git_text(git, root, ["rev-parse", "--verify", "HEAD^{commit}"]) != source:
        raise ValueError("correction integration changed the original checkout HEAD")
    if _git(git, root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]):
        raise ValueError("correction integration original checkout is not clean")
    if _git(git, worktree, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]):
        raise ValueError("correction integration worktree is not clean")
    names = tuple(
        sorted(
            path.decode("utf-8")
            for path in _git(
                git,
                worktree,
                ["diff", "--name-only", "-z", "--no-renames", source, integrated],
            ).split(b"\x00")
            if path
        )
    )
    if names != receipt.execution.changed_paths:
        raise ValueError("correction integration changed paths outside proposal")
    replacement = {
        item.path: item for item in receipt.signed_proposal.proposal.replacements
    }
    for path in names:
        if _read_repository_file(worktree, path) != replacement[path].content:
            raise ValueError("correction integration bytes differ from signed proposal")
        if (
            _git(git, worktree, ["show", f"{integrated}:{path}"], limit=1_000_001)
            != replacement[path].content
        ):
            raise ValueError("correction integration Git blob differs from proposal")
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
        raise ValueError("correction integration produced an empty patch")
    tree = _git_text(git, worktree, ["rev-parse", f"{integrated}^{{tree}}"])
    return integrated, tree, patch


def integrate_correction_child(
    *,
    admission: G4CorrectionCycleAdmission,
    receipt: G4CorrectionChildDispatchReceipt,
    approval: SignedG4CorrectionIntegrationApproval,
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
    integration_store: Path,
    now: datetime | None = None,
) -> G4CorrectionIntegrationRecord:
    """Consume one grant and commit exactly the proposal in a new private worktree."""
    current = _utc(now if now is not None else datetime.now(UTC))
    root, store, name = _check_original_inputs(
        admission=admission,
        receipt=receipt,
        approval=approval,
        first=first,
        provenance=provenance,
        controls=controls,
        binding=binding,
        package=package,
        reviewer_package_path=reviewer_package_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        candidate_dispatch_store=candidate_dispatch_store,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
        integration_store=integration_store,
        now=current,
    )
    worktree = store / name
    if worktree.exists() or worktree.is_symlink():
        raise ValueError("correction integration worktree already exists")
    _claim(store, name, approval)
    source = approval.approval.source_revision
    _git(
        git_executable,
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
            source,
        ],
        limit=4096,
    )
    if worktree.resolve(strict=True) != worktree or not worktree.is_dir():
        raise ValueError("correction integration worktree path changed")
    if (
        _git_text(git_executable, worktree, ["rev-parse", "--verify", "HEAD^{commit}"])
        != source
    ):
        raise ValueError("correction worktree checked out another source")
    if _git(
        git_executable,
        worktree,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ):
        raise ValueError("correction worktree checkout is not clean")
    original = {item.path: item for item in receipt.offer.source_files}
    replacement = {
        item.path: item for item in receipt.signed_proposal.proposal.replacements
    }
    for path in receipt.execution.changed_paths:
        _write_existing_file(
            worktree, path, original[path].content, replacement[path].content
        )
    _git(
        git_executable,
        worktree,
        ["-c", "core.autocrlf=false", "add", "--", *receipt.execution.changed_paths],
        limit=4096,
    )
    staged = tuple(
        sorted(
            path.decode("utf-8")
            for path in _git(
                git_executable, worktree, ["diff", "--cached", "--name-only", "-z"]
            ).split(b"\x00")
            if path
        )
    )
    if staged != receipt.execution.changed_paths:
        raise ValueError("correction integration staged unexpected paths")
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
            "commit",
            "-m",
            f"G4 correction {approval.approval.integration_id}",
        ],
        limit=4096,
    )
    integrated, tree, patch = _verify_integrated_git(
        git=git_executable, root=root, worktree=worktree, source=source, receipt=receipt
    )
    replayed = record_trusted_git_provenance(
        repository_id=provenance.git_provenance.provenance.repository_id,
        repository_root=root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        binding=binding,
        reviewer_package_path=reviewer_package_path,
        assignment=provenance.child_assignment,
        result=provenance.child_result,
    )
    if replayed != provenance.git_provenance.provenance:
        raise ValueError("original source changed during correction integration")
    return G4CorrectionIntegrationRecord(
        approval=approval,
        child_dispatch_receipt_sha256=digest(canonical_bytes(receipt)),
        source_revision=source,
        integrated_revision=integrated,
        integrated_tree_id=tree,
        patch_sha256=digest(patch),
        patch_bytes=len(patch),
        changed_paths=receipt.execution.changed_paths,
        worktree_name=name,
        integrated_at=current,
    )


def verify_correction_integration_record(
    signed: SignedG4CorrectionIntegrationRecord,
    *,
    admission: G4CorrectionCycleAdmission,
    receipt: G4CorrectionChildDispatchReceipt,
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
    integration_store: Path,
) -> None:
    """Replay the signed VCS record and exact Git bytes without granting acceptance."""
    record = signed.record
    verify_provenance_signature(
        record.approval.approval,
        record.approval.signature,
        provenance.policy,
        "creator",
        _APPROVAL_DOMAIN,
    )
    verify_provenance_signature(
        record, signed.signature, provenance.policy, "vcs", _RECORD_DOMAIN
    )
    if (
        record.approval.approval.policy_sha256 != provenance.policy.policy_sha256
        or record.approval.approval.repository_id
        != provenance.git_provenance.provenance.repository_id
        or record.source_revision
        != provenance.git_provenance.provenance.source_revision
        or record.child_dispatch_receipt_sha256 != digest(canonical_bytes(receipt))
        or not record.approval.approval.issued_at
        <= record.integrated_at
        < record.approval.approval.expires_at
    ):
        raise ValueError("correction integration record differs from signed inputs")
    root, store, expected_name = _check_original_inputs(
        admission=admission,
        receipt=receipt,
        approval=record.approval,
        first=first,
        provenance=provenance,
        controls=controls,
        binding=binding,
        package=package,
        reviewer_package_path=reviewer_package_path,
        repository_root=repository_root,
        implementation_root=implementation_root,
        git_executable=git_executable,
        candidate_dispatch_store=candidate_dispatch_store,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
        integration_store=integration_store,
        now=record.integrated_at,
    )
    if record.worktree_name != expected_name:
        raise ValueError("correction integration worktree name differs from task")
    _verify_claim(store, record.worktree_name, record.approval)
    worktree = store / record.worktree_name
    if not worktree.is_dir() or worktree.resolve(strict=True) != worktree:
        raise ValueError("correction integration worktree moved")
    integrated, tree, patch = _verify_integrated_git(
        git=git_executable,
        root=root,
        worktree=worktree,
        source=record.source_revision,
        receipt=receipt,
    )
    if (
        integrated != record.integrated_revision
        or tree != record.integrated_tree_id
        or digest(patch) != record.patch_sha256
        or len(patch) != record.patch_bytes
        or record.changed_paths != receipt.execution.changed_paths
    ):
        raise ValueError("correction integration record differs from current Git")
