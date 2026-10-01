"""One-use creator metadata addition preserving a signed initial-child commit."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import base64
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_initial_integration import (
    _APPROVAL_DOMAIN,
    _RECORD_DOMAIN,
    SignedG4InitialIntegrationRecord,
)
from mos_eisley.reviewer_provenance import (
    _CREATOR_DOMAIN,
    _REVIEWER_DOMAIN,
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    SignedG4CreatorApproval,
    SignedG4ReviewerCustody,
    SourceRevision,
    _git,
    _git_text,
    verify_provenance_signature,
)

DOMAIN = b"mos-eisley/g4-creator-metadata-amendment/v1\x00"
RECORD_DOMAIN = b"mos-eisley/g4-creator-metadata-record/v1\x00"
DECLARATION = "# Standard library only; no third-party runtime dependencies.\n"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("metadata times require UTC")
    return value


class G4CreatorMetadataAmendment(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_creator_metadata_amendment"] = "g4_creator_metadata_amendment"
    amendment_id: Identifier
    policy_sha256: Digest
    creator_artifact_sha256: Digest
    custody_artifact_sha256: Digest
    signed_initial_vcs_sha256: Digest
    parent_revision: SourceRevision
    parent_tree_id: SourceRevision
    parent_root_sha256: Digest
    amendment_store_sha256: Digest
    metadata_path: Literal["requirements.lock"] = "requirements.lock"
    metadata_content: Literal[
        "# Standard library only; no third-party runtime dependencies.\n"
    ] = DECLARATION
    issued_at: datetime
    expires_at: datetime
    isolated_metadata_write_authorized: Literal[True] = True
    original_source_write_authorized: Literal[False] = False
    child_source_write_authorized: Literal[False] = False
    plan_or_test_mutation_authorized: Literal[False] = False
    candidate_execution_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def window(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=1):
            raise ValueError("metadata authority exceeds one hour")
        return self


class SignedG4CreatorMetadataAmendment(Contract):
    amendment: G4CreatorMetadataAmendment
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _signature(
    value: Contract, key: Ed25519PrivateKey, signer_id: str, domain: bytes
) -> G4ArtifactSignature:
    return G4ArtifactSignature(
        signer_id=signer_id,
        public_key_sha256=digest(key.public_key().public_bytes_raw()),
        signature_base64=base64.b64encode(
            key.sign(domain + canonical_bytes(value))
        ).decode(),
    )


def sign_creator_metadata_amendment(
    amendment: G4CreatorMetadataAmendment, signer_id: str, key: Ed25519PrivateKey
) -> SignedG4CreatorMetadataAmendment:
    return SignedG4CreatorMetadataAmendment(
        amendment=amendment, signature=_signature(amendment, key, signer_id, DOMAIN)
    )


def _parent(git: Path, root: Path, vcs: SignedG4InitialIntegrationRecord) -> None:
    record = vcs.record
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise ValueError("metadata parent must be a canonical nonsymlink root")
    if (
        _git_text(git, root, ["rev-parse", "--show-toplevel"]) != str(root)
        or _git_text(git, root, ["rev-parse", "HEAD"]) != record.integrated_revision
        or _git_text(git, root, ["rev-parse", "HEAD^{tree}"])
        != record.integrated_tree_id
        or _git_text(git, root, ["rev-parse", "HEAD^1"]) != record.source_revision
        or _git(git, root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    ):
        raise ValueError("signed metadata parent Git identity or cleanliness changed")
    patch = _git(
        git,
        root,
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            record.source_revision,
            record.integrated_revision,
        ],
    )
    if digest(patch) != record.patch_sha256 or len(patch) != record.patch_bytes:
        raise ValueError("signed initial Git patch changed")
    if _git(git, root, ["ls-tree", "-z", "HEAD", "--", "requirements.lock"]):
        raise ValueError("metadata amendment cannot replace an existing declaration")


def prepare_creator_metadata_amendment(
    *,
    amendment_id: str,
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    custody: SignedG4ReviewerCustody,
    vcs: SignedG4InitialIntegrationRecord,
    parent_root: Path,
    store: Path,
    git: Path,
    issued: datetime,
    expires: datetime,
) -> G4CreatorMetadataAmendment:
    verify_provenance_signature(
        creator.approval, creator.signature, policy, "creator", _CREATOR_DOMAIN
    )
    verify_provenance_signature(
        custody.custody, custody.signature, policy, "reviewer", _REVIEWER_DOMAIN
    )
    verify_provenance_signature(
        vcs.record, vcs.signature, policy, "vcs", _RECORD_DOMAIN
    )
    verify_provenance_signature(
        vcs.record.approval.approval,
        vcs.record.approval.signature,
        policy,
        "creator",
        _APPROVAL_DOMAIN,
    )
    if (
        custody.custody.creator_approval_artifact_sha256 != creator.artifact_sha256
        or creator.approval.base_revision != vcs.record.source_revision
        or creator.approval.policy_sha256 != policy.policy_sha256
        or custody.custody.policy_sha256 != policy.policy_sha256
        or vcs.record.approval.approval.policy_sha256 != policy.policy_sha256
        or creator.signature.signer_id != vcs.record.approval.signature.signer_id
        or creator.signature.public_key_sha256
        != vcs.record.approval.signature.public_key_sha256
        or not policy.valid_from
        <= creator.approval.issued_at
        <= custody.custody.issued_at
        <= vcs.record.integrated_at
        <= issued
        < expires
        <= policy.valid_until
    ):
        raise ValueError(
            "metadata authority differs from original custody or chronology"
        )
    _parent(git, parent_root, vcs)
    if store.is_symlink() or store.resolve(strict=True) != store:
        raise ValueError("metadata store must be canonical")
    fd = open_private_dispatch_store(store)
    os.close(fd)
    if store.is_relative_to(parent_root) or parent_root.is_relative_to(store):
        raise ValueError("metadata state overlaps parent source")
    return G4CreatorMetadataAmendment(
        amendment_id=amendment_id,
        policy_sha256=policy.policy_sha256,
        creator_artifact_sha256=creator.artifact_sha256,
        custody_artifact_sha256=custody.artifact_sha256,
        signed_initial_vcs_sha256=digest(canonical_bytes(vcs)),
        parent_revision=vcs.record.integrated_revision,
        parent_tree_id=vcs.record.integrated_tree_id,
        parent_root_sha256=digest(str(parent_root).encode()),
        amendment_store_sha256=digest(str(store).encode()),
        issued_at=issued,
        expires_at=expires,
    )


def verify_creator_metadata_amendment(
    signed: SignedG4CreatorMetadataAmendment,
    *,
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    custody: SignedG4ReviewerCustody,
    vcs: SignedG4InitialIntegrationRecord,
    parent_root: Path,
    store: Path,
    git: Path,
    now: datetime,
) -> None:
    signer = verify_provenance_signature(
        signed.amendment, signed.signature, policy, "creator", DOMAIN
    )
    a = signed.amendment
    expected = prepare_creator_metadata_amendment(
        amendment_id=a.amendment_id,
        policy=policy,
        creator=creator,
        custody=custody,
        vcs=vcs,
        parent_root=parent_root,
        store=store,
        git=git,
        issued=a.issued_at,
        expires=a.expires_at,
    )
    if (
        a != expected
        or signer.signer_id != creator.signature.signer_id
        or signer.public_key_sha256 != creator.signature.public_key_sha256
        or not a.issued_at <= now < a.expires_at
    ):
        raise ValueError("metadata grant changed, expired or signed by another owner")


class G4CreatorMetadataRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_creator_metadata_record"] = "g4_creator_metadata_record"
    amendment: SignedG4CreatorMetadataAmendment
    revision: SourceRevision
    tree_id: SourceRevision
    worktree_name: Identifier
    patch_sha256: Digest
    amended_at: datetime
    parent_source_unchanged: Literal[True] = True
    child_source_and_tests_unchanged: Literal[True] = True
    candidate_execution_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("amended_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _name(signed: SignedG4CreatorMetadataAmendment) -> str:
    return "g4-metadata-" + signed.artifact_sha256[:24]


def _claim_bytes(
    store: Path, name: str, signed: SignedG4CreatorMetadataAmendment
) -> None:
    path = store / (name + ".claim")
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_size > 1_000_000
        or path.is_symlink()
        or path.stat().st_mode & 0o077
        or path.read_bytes() != canonical_bytes(signed)
    ):
        raise ValueError("metadata claim differs from exact grant")


def _common(git: Path, root: Path) -> Path:
    path = Path(_git_text(git, root, ["rev-parse", "--git-common-dir"]))
    return (path if path.is_absolute() else root / path).resolve(strict=True)


def _amended_git(
    git: Path, root: Path, signed: SignedG4CreatorMetadataAmendment, parent_root: Path
) -> tuple[str, str, bytes]:
    a = signed.amendment
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise ValueError("metadata worktree is not canonical")
    if (
        _git_text(git, root, ["rev-parse", "--show-toplevel"]) != str(root)
        or _common(git, root) != _common(git, parent_root)
        or _git_text(git, root, ["rev-list", "--parents", "-n", "1", "HEAD"])
        != _git_text(git, root, ["rev-parse", "HEAD"]) + " " + a.parent_revision
        or _git(git, root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        or _git(git, root, ["diff", "--name-only", "-z", a.parent_revision, "HEAD"])
        != b"requirements.lock\0"
    ):
        raise ValueError("metadata commit changed paths, ancestry or cleanliness")
    path = root / "requirements.lock"
    if path.is_symlink() or path.read_bytes() != DECLARATION.encode():
        raise ValueError("metadata declaration differs from authority")
    if _git(git, root, ["show", "HEAD:requirements.lock"]) != DECLARATION.encode():
        raise ValueError("metadata committed blob differs")
    patch = _git(
        git,
        root,
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            a.parent_revision,
            "HEAD",
        ],
    )
    return (
        _git_text(git, root, ["rev-parse", "HEAD"]),
        _git_text(git, root, ["rev-parse", "HEAD^{tree}"]),
        patch,
    )


def amend_creator_metadata_once(
    signed: SignedG4CreatorMetadataAmendment,
    *,
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    custody: SignedG4ReviewerCustody,
    vcs: SignedG4InitialIntegrationRecord,
    parent_root: Path,
    store: Path,
    git: Path,
    now: datetime | None = None,
) -> G4CreatorMetadataRecord:
    current = now or datetime.now(UTC)
    verify_creator_metadata_amendment(
        signed,
        policy=policy,
        creator=creator,
        custody=custody,
        vcs=vcs,
        parent_root=parent_root,
        store=store,
        git=git,
        now=current,
    )
    name = _name(signed)
    if (store / name).exists() or (store / name).is_symlink():
        raise ValueError("metadata worktree already exists")
    fd = open_private_dispatch_store(store)
    try:
        claim = os.open(
            name + ".claim",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(claim, "wb") as stream:
            stream.write(canonical_bytes(signed))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)
    _parent(git, parent_root, vcs)
    root = store / name
    _git(
        git,
        parent_root,
        [
            "-c",
            "core.autocrlf=false",
            "worktree",
            "add",
            "--detach",
            str(root),
            signed.amendment.parent_revision,
        ],
    )
    path = root / "requirements.lock"
    file_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(file_fd, "wb") as stream:
        stream.write(DECLARATION.encode())
        stream.flush()
        os.fsync(stream.fileno())
    _git(git, root, ["-c", "core.autocrlf=false", "add", "--", "requirements.lock"])
    if (
        _git(git, root, ["diff", "--cached", "--name-only", "-z"])
        != b"requirements.lock\0"
    ):
        raise ValueError("metadata staging changed another path")
    _git(
        git,
        root,
        [
            "-c",
            "user.name=Joshua Myers",
            "-c",
            "user.email=local-g4@example.invalid",
            "commit",
            "--no-gpg-sign",
            "-m",
            "Add authorized standard-library dependency declaration",
        ],
    )
    revision, tree, patch = _amended_git(git, root, signed, parent_root)
    _parent(git, parent_root, vcs)
    return G4CreatorMetadataRecord(
        amendment=signed,
        revision=revision,
        tree_id=tree,
        worktree_name=name,
        patch_sha256=digest(patch),
        amended_at=current,
    )


def verify_creator_metadata_record(
    record: G4CreatorMetadataRecord,
    *,
    policy: G4ProvenanceTrustPolicy,
    creator: SignedG4CreatorApproval,
    custody: SignedG4ReviewerCustody,
    vcs: SignedG4InitialIntegrationRecord,
    parent_root: Path,
    store: Path,
    git: Path,
) -> None:
    verify_creator_metadata_amendment(
        record.amendment,
        policy=policy,
        creator=creator,
        custody=custody,
        vcs=vcs,
        parent_root=parent_root,
        store=store,
        git=git,
        now=record.amended_at,
    )
    if record.worktree_name != _name(record.amendment):
        raise ValueError("metadata record names another worktree")
    _claim_bytes(store, record.worktree_name, record.amendment)
    revision, tree, patch = _amended_git(
        git, store / record.worktree_name, record.amendment, parent_root
    )
    if (record.revision, record.tree_id, record.patch_sha256) != (
        revision,
        tree,
        digest(patch),
    ):
        raise ValueError("metadata record differs from exact Git")


class SignedG4CreatorMetadataRecord(Contract):
    record: G4CreatorMetadataRecord
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_creator_metadata_record(
    record: G4CreatorMetadataRecord,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4CreatorMetadataRecord:
    return SignedG4CreatorMetadataRecord(
        record=record, signature=_signature(record, key, signer_id, RECORD_DOMAIN)
    )


def verify_creator_metadata_record_signature(
    signed: SignedG4CreatorMetadataRecord,
    policy: G4ProvenanceTrustPolicy,
) -> None:
    verify_provenance_signature(
        signed.record, signed.signature, policy, "vcs", RECORD_DOMAIN
    )
