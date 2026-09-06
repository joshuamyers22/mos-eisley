"""Atomic inert installation of one authorized quarantined persona package."""

from __future__ import annotations

import fcntl
import os
import re
import stat
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from secrets import token_hex
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.skills import (
    ArchivedSkillFile,
    SkillDescriptor,
    SkillIdentity,
    SkillPackageArchive,
)
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan
from mos_eisley.evaluation.skill_comparison import (
    SealedSkillComparison,
    SkillComparisonReport,
    SkillHoldoutUseClaim,
)
from mos_eisley.evaluation.skill_promotion import (
    AuthenticatedSkillPromotion,
    SkillEvaluationLineage,
    SkillPromotionAuthorityPolicy,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.skill_installation import (
    AuthenticatedSkillInstallation,
    SkillInstallationAuthorityPolicy,
    SkillInstallationClaim,
    SkillInstallationClaimStore,
    SkillInstallationClaimStorePolicy,
    guard_and_claim_skill_installation,
    verify_signed_skill_installation_decision,
)
from mos_eisley.run.skill_release import SkillReleaseEvidence
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAuthorityPolicy,
)
from mos_eisley.run.skill_staging import SkillStagingManifest, SkillStagingStore
from mos_eisley.run.skills import verify_skill_archive
from mos_eisley.run.store import private_write

UtcTimestamp = Annotated[datetime, Field()]
_TRANSACTION_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_ROOT_ENTRIES = frozenset({"policy.json", "packages", "transactions", "install.lock"})
_TRANSACTION_TOP_LEVEL = frozenset(
    {
        "intent.json",
        "authorization.json",
        "claim.json",
        "staging-manifest.json",
        "manifest.json",
        "payload",
    }
)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class SkillInstalledStorePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_installed_store_policy"] = "skill_installed_store_policy"
    store_id: Digest
    installation_authority_policy_sha256: Digest
    staging_store_policy_sha256: Digest
    claim_store_policy_sha256: Digest
    max_packages: Annotated[int, Field(ge=1, le=10_000)] = 1000
    max_incomplete_transactions: Annotated[int, Field(ge=1, le=1000)] = 100
    default_mutation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class InstalledSkillFile(Contract):
    path: Annotated[str, Field(min_length=1, max_length=1024)]
    content_sha256: Digest
    byte_count: Annotated[int, Field(ge=0, le=1_000_000)]

    @model_validator(mode="after")
    def safe_relative_path(self) -> Self:
        parts = self.path.split("/")
        if (
            self.path.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
            or len(parts) > 4
            or "\x00" in self.path
        ):
            raise ValueError("installed skill path is invalid")
        return self


class SkillInstallIntent(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_install_intent"] = "skill_install_intent"
    transaction_id: Identifier
    installed_store_policy_sha256: Digest
    installation_authority_policy_sha256: Digest
    authorization_sha256: Digest
    decision_sha256: Digest
    claim_store_policy_sha256: Digest
    claim_sha256: Digest
    staging_store_policy_sha256: Digest
    staging_manifest_sha256: Digest
    control_anchor_entry_sha256: Digest
    action: Literal["candidate", "rollback"]
    archive_sha256: Digest
    skill: SkillIdentity
    started_at: UtcTimestamp
    installation_authorized: Literal[True] = True
    default_mutation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False

    @field_validator("started_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @property
    def intent_sha256(self) -> str:
        return digest(canonical_bytes(self))


class InstalledSkillManifest(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["installed_inert_skill_package"] = "installed_inert_skill_package"
    intent: SkillInstallIntent
    descriptor: SkillDescriptor
    files: Annotated[tuple[InstalledSkillFile, ...], Field(min_length=1, max_length=64)]
    installed_at: UtcTimestamp
    installation_performed: Literal[True] = True
    default_changed: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False

    @field_validator("installed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_package(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if tuple(sorted(set(paths))) != paths:
            raise ValueError("installed skill files must be unique and sorted")
        if (
            self.intent.skill != self.descriptor.identity
            or self.descriptor.file_count != len(self.files)
            or self.descriptor.package_bytes
            != sum(item.byte_count for item in self.files)
            or self.installed_at < self.intent.started_at
        ):
            raise ValueError("installed skill manifest does not match its intent")
        return self

    @property
    def manifest_sha256(self) -> str:
        return digest(canonical_bytes(self))


class IncompleteSkillInstallTransaction(Contract):
    transaction_id: Identifier
    intent_present: bool
    authorization_present: bool
    claim_present: bool
    staging_manifest_present: bool
    completion_manifest_present: bool
    decision_sha256: Digest | None = None
    archive_sha256: Digest | None = None


class SkillInstalledStoreSnapshot(Contract):
    schema_version: Literal[1] = 1
    policy: SkillInstalledStorePolicy
    packages: Annotated[tuple[Digest, ...], Field(max_length=10_000)]
    incomplete: Annotated[
        tuple[IncompleteSkillInstallTransaction, ...], Field(max_length=1000)
    ]

    @model_validator(mode="after")
    def canonical_inventory(self) -> Self:
        if tuple(sorted(set(self.packages))) != self.packages:
            raise ValueError("installed package inventory must be unique and sorted")
        transaction_ids = tuple(item.transaction_id for item in self.incomplete)
        if tuple(sorted(set(transaction_ids))) != transaction_ids:
            raise ValueError(
                "incomplete install transactions must be unique and sorted"
            )
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillInstallResult(Contract):
    schema_version: Literal[1] = 1
    manifest: InstalledSkillManifest
    package_path: Annotated[str, Field(min_length=1, max_length=4096)]
    claim: SkillInstallationClaim
    installation_performed: Literal[True] = True
    default_changed: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False


class SkillInstallRecoveryEntry(Contract):
    decision_sha256: Digest
    authorization_sha256: Digest
    archive_sha256: Digest
    state: Literal["completed", "incomplete", "claim_only"]
    transaction_id: Identifier | None = None
    installed_manifest_sha256: Digest | None = None

    @model_validator(mode="after")
    def state_fields(self) -> Self:
        if self.state == "completed":
            if (
                self.installed_manifest_sha256 is None
                or self.transaction_id is not None
            ):
                raise ValueError("completed recovery entry fields are invalid")
        elif self.state == "incomplete":
            if (
                self.transaction_id is None
                or self.installed_manifest_sha256 is not None
            ):
                raise ValueError("incomplete recovery entry fields are invalid")
        elif (
            self.transaction_id is not None
            or self.installed_manifest_sha256 is not None
        ):
            raise ValueError("claim-only recovery entry fields are invalid")
        return self


class SkillInstallRecoverySnapshot(Contract):
    schema_version: Literal[1] = 1
    installed_store_policy_sha256: Digest
    claim_store_policy_sha256: Digest
    entries: Annotated[tuple[SkillInstallRecoveryEntry, ...], Field(max_length=100_000)]
    unbound_transactions: Annotated[tuple[Identifier, ...], Field(max_length=1000)]
    automatic_recovery_authorized: Literal[False] = False
    cleanup_authorized: Literal[False] = False
    default_mutation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def canonical_entries(self) -> Self:
        identities = tuple(item.decision_sha256 for item in self.entries)
        if tuple(sorted(set(identities))) != identities:
            raise ValueError("install recovery entries must be unique and sorted")
        if tuple(sorted(set(self.unbound_transactions))) != self.unbound_transactions:
            raise ValueError("unbound install transactions must be unique and sorted")
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _validate_private_directory(path: Path, label: str) -> None:
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"{label} must be a non-symlink directory")
    if metadata.st_uid != os.getuid():
        raise ValueError(f"{label} must be owned by current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError(f"{label} must be private")


def _validate_private_file(path: Path, label: str) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"{label} must be a non-symlink regular file")
    if metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
        raise ValueError(f"{label} ownership or link count is invalid")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError(f"{label} must have mode 0600")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _directory_inventory(root: Path) -> tuple[tuple[str, bool], ...]:
    entries: list[tuple[str, bool]] = []

    def visit(path: Path, prefix: tuple[str, ...]) -> None:
        with os.scandir(path) as children:
            ordered = sorted(children, key=lambda item: item.name)
        for child in ordered:
            child_path = Path(child.path)
            metadata = child_path.lstat()
            relative = PurePosixPath(*prefix, child.name).as_posix()
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("installed package cannot contain symlinks")
            if stat.S_ISDIR(metadata.st_mode):
                _validate_private_directory(child_path, "installed package directory")
                entries.append((relative, True))
                visit(child_path, (*prefix, child.name))
            elif stat.S_ISREG(metadata.st_mode):
                _validate_private_file(child_path, "installed package file")
                entries.append((relative, False))
            else:
                raise ValueError("installed package contains a special file")
            if len(entries) > 320:
                raise ValueError("installed package inventory exceeds its limit")

    visit(root, ())
    return tuple(entries)


def _fsync_tree_directories(root: Path) -> None:
    directories = [
        root / relative
        for relative, is_directory in _directory_inventory(root)
        if is_directory
    ]
    for path in reversed(directories):
        _fsync_directory(path)
    _fsync_directory(root)


def _expected_inventory(
    manifest: InstalledSkillManifest,
) -> tuple[tuple[str, bool], ...]:
    directories = {"payload"}
    for item in manifest.files:
        parts = PurePosixPath(item.path).parts[:-1]
        for index in range(1, len(parts) + 1):
            directories.add(PurePosixPath("payload", *parts[:index]).as_posix())
    files = {
        "intent.json",
        "authorization.json",
        "claim.json",
        "staging-manifest.json",
        "manifest.json",
    } | {PurePosixPath("payload", item.path).as_posix() for item in manifest.files}
    return tuple(
        sorted(
            (
                *((item, True) for item in directories),
                *((item, False) for item in files),
            )
        )
    )


def _verify_installed_package(
    path: Path,
    policy: SkillInstalledStorePolicy,
    installation_policy: SkillInstallationAuthorityPolicy,
    expected_archive: SkillPackageArchive | None = None,
) -> tuple[
    InstalledSkillManifest,
    SkillPackageArchive,
    AuthenticatedSkillInstallation,
    SkillInstallationClaim,
]:
    _validate_private_directory(path, "installed package")
    manifest_path = path / "manifest.json"
    _validate_private_file(manifest_path, "installed package manifest")
    manifest_payload = read_bounded(manifest_path, 128_000)
    manifest = InstalledSkillManifest.model_validate_json(manifest_payload)
    intent_path = path / "intent.json"
    authorization_path = path / "authorization.json"
    claim_path = path / "claim.json"
    staging_manifest_path = path / "staging-manifest.json"
    for item, label in (
        (intent_path, "installed package intent"),
        (authorization_path, "installed package authorization"),
        (claim_path, "installed package claim"),
        (staging_manifest_path, "installed package staging manifest"),
    ):
        _validate_private_file(item, label)
    authorization = AuthenticatedSkillInstallation.model_validate_json(
        read_bounded(authorization_path, 256_000)
    )
    claim = SkillInstallationClaim.model_validate_json(
        read_bounded(claim_path, 128_000)
    )
    staging_manifest = SkillStagingManifest.model_validate_json(
        read_bounded(staging_manifest_path, 128_000)
    )
    if (
        manifest_payload != canonical_bytes(manifest)
        or read_bounded(intent_path, 128_000) != canonical_bytes(manifest.intent)
        or read_bounded(authorization_path, 256_000) != canonical_bytes(authorization)
        or read_bounded(claim_path, 128_000) != canonical_bytes(claim)
        or read_bounded(staging_manifest_path, 128_000)
        != canonical_bytes(staging_manifest)
        or _directory_inventory(path) != _expected_inventory(manifest)
    ):
        raise ValueError("installed package provenance or inventory is invalid")
    verify_signed_skill_installation_decision(
        authorization.signed_decision, installation_policy
    )
    intent = manifest.intent
    decision = authorization.signed_decision.decision
    if (
        intent.installed_store_policy_sha256 != policy.policy_sha256
        or intent.installation_authority_policy_sha256
        != installation_policy.policy_sha256
        or intent.authorization_sha256 != authorization.authorization_sha256
        or intent.decision_sha256 != decision.decision_sha256
        or intent.claim_store_policy_sha256 != claim.claim_store_policy_sha256
        or intent.claim_sha256 != claim.claim_sha256
        or intent.staging_store_policy_sha256 != decision.staging_store_policy_sha256
        or intent.staging_manifest_sha256 != staging_manifest.manifest_sha256
        or intent.control_anchor_entry_sha256 != decision.control_anchor_entry_sha256
        or intent.action != decision.action
        or intent.archive_sha256 != decision.archive_sha256
        or intent.skill != decision.skill
        or claim.authorization_sha256 != authorization.authorization_sha256
        or claim.decision_sha256 != decision.decision_sha256
        or claim.archive_sha256 != decision.archive_sha256
        or claim.installation_target_id != policy.store_id
        or staging_manifest.intent.archive_sha256 != decision.archive_sha256
        or staging_manifest.intent.action != decision.action
        or staging_manifest.intent.skill != decision.skill
    ):
        raise ValueError("installed package sources do not match its manifest")
    archived_files: list[ArchivedSkillFile] = []
    for item in manifest.files:
        payload = read_bounded(path / "payload" / item.path, item.byte_count)
        if len(payload) != item.byte_count or digest(payload) != item.content_sha256:
            raise ValueError("installed package payload differs from its manifest")
        archived_files.append(ArchivedSkillFile.retain(item.path, payload))
    archive = SkillPackageArchive(
        descriptor=manifest.descriptor,
        files=tuple(archived_files),
    )
    verify_skill_archive(archive)
    if archive.archive_sha256 != intent.archive_sha256:
        raise ValueError("installed package archive differs from its intent")
    if expected_archive is not None and archive != expected_archive:
        raise ValueError("installed package differs from selected staging archive")
    return manifest, archive, authorization, claim


class SkillInstalledStore:
    """Private installed bytes with no default pointer or runtime reader."""

    def __init__(self, root: Path):
        self.root = root.absolute()
        self._validate_layout()
        payload = read_bounded(self.root / "policy.json", 64_000)
        self.policy = SkillInstalledStorePolicy.model_validate_json(payload)
        if payload != canonical_bytes(self.policy):
            raise ValueError("skill installed store policy is not canonical")

    @classmethod
    def create(
        cls,
        root: Path,
        policy: SkillInstalledStorePolicy,
        installation_policy: SkillInstallationAuthorityPolicy,
        staging_store: SkillStagingStore,
        claim_store_policy: SkillInstallationClaimStorePolicy,
    ) -> SkillInstalledStore:
        policy = SkillInstalledStorePolicy.model_validate_json(canonical_bytes(policy))
        installation_policy = SkillInstallationAuthorityPolicy.model_validate_json(
            canonical_bytes(installation_policy)
        )
        claim_store_policy = SkillInstallationClaimStorePolicy.model_validate_json(
            canonical_bytes(claim_store_policy)
        )
        if (
            policy.store_id != installation_policy.installation_target_id
            or policy.installation_authority_policy_sha256
            != installation_policy.policy_sha256
            or policy.staging_store_policy_sha256 != staging_store.policy.policy_sha256
            or policy.claim_store_policy_sha256 != claim_store_policy.policy_sha256
            or installation_policy.staging_store_policy_sha256
            != staging_store.policy.policy_sha256
            or installation_policy.claim_store_id != claim_store_policy.store_id
            or claim_store_policy.authority_policy_sha256
            != installation_policy.policy_sha256
        ):
            raise ValueError(
                "installed store policy does not match its trusted sources"
            )
        root.mkdir(mode=0o700)
        private_write(root / "policy.json", canonical_bytes(policy))
        private_write(root / "install.lock", b"")
        (root / "packages").mkdir(mode=0o700)
        (root / "transactions").mkdir(mode=0o700)
        _fsync_directory(root)
        _fsync_directory(root.parent)
        return cls(root)

    @property
    def packages_path(self) -> Path:
        return self.root / "packages"

    @property
    def transactions_path(self) -> Path:
        return self.root / "transactions"

    def _validate_layout(self) -> None:
        _validate_private_directory(self.root, "skill installed store")
        if {item.name for item in os.scandir(self.root)} != set(_ROOT_ENTRIES):
            raise ValueError("skill installed store root inventory is invalid")
        _validate_private_file(self.root / "policy.json", "installed store policy")
        _validate_private_file(self.root / "install.lock", "installed store lock")
        _validate_private_directory(
            self.root / "packages", "installed packages directory"
        )
        _validate_private_directory(
            self.root / "transactions", "installed transactions directory"
        )

    @contextmanager
    def _locked(self) -> Generator[None, None, None]:
        lock_path = self.root / "install.lock"
        before = lock_path.lstat()
        descriptor = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise ValueError("installed store lock changed during acquisition")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            after = lock_path.lstat()
            if (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError("installed store lock changed while locked")
            self._validate_layout()
            yield
        finally:
            os.close(descriptor)

    def _snapshot_unlocked(
        self,
        installation_policy: SkillInstallationAuthorityPolicy,
    ) -> SkillInstalledStoreSnapshot:
        if (
            self.policy.installation_authority_policy_sha256
            != installation_policy.policy_sha256
        ):
            raise ValueError("installed store does not match installation policy")
        package_names: list[str] = []
        with os.scandir(self.packages_path) as package_entries:
            for entry in package_entries:
                if re.fullmatch(r"[0-9a-f]{64}", entry.name) is None:
                    raise ValueError("installed package name is invalid")
                _, archive, _, _ = _verify_installed_package(
                    Path(entry.path), self.policy, installation_policy
                )
                if archive.archive_sha256 != entry.name:
                    raise ValueError("installed package path digest is invalid")
                package_names.append(entry.name)
        incomplete: list[IncompleteSkillInstallTransaction] = []
        with os.scandir(self.transactions_path) as transaction_entries:
            for entry in transaction_entries:
                if _TRANSACTION_PATTERN.fullmatch(entry.name) is None:
                    raise ValueError("skill install transaction name is invalid")
                path = Path(entry.path)
                _validate_private_directory(path, "incomplete install transaction")
                names = {item.name for item in os.scandir(path)}
                if not names <= _TRANSACTION_TOP_LEVEL:
                    raise ValueError(
                        "incomplete install transaction inventory is invalid"
                    )
                intent: SkillInstallIntent | None = None
                authorization: AuthenticatedSkillInstallation | None = None
                claim: SkillInstallationClaim | None = None
                staging_manifest: SkillStagingManifest | None = None
                intent_path = path / "intent.json"
                if "intent.json" in names:
                    _validate_private_file(intent_path, "incomplete install intent")
                    payload = read_bounded(intent_path, 128_000)
                    intent = SkillInstallIntent.model_validate_json(payload)
                    if payload != canonical_bytes(intent):
                        raise ValueError("incomplete install intent is not canonical")
                authorization_path = path / "authorization.json"
                if "authorization.json" in names:
                    _validate_private_file(
                        authorization_path, "incomplete install authorization"
                    )
                    payload = read_bounded(authorization_path, 256_000)
                    authorization = AuthenticatedSkillInstallation.model_validate_json(
                        payload
                    )
                    if payload != canonical_bytes(authorization):
                        raise ValueError(
                            "incomplete install authorization is not canonical"
                        )
                    verify_signed_skill_installation_decision(
                        authorization.signed_decision, installation_policy
                    )
                claim_path = path / "claim.json"
                if "claim.json" in names:
                    _validate_private_file(claim_path, "incomplete install claim")
                    payload = read_bounded(claim_path, 128_000)
                    claim = SkillInstallationClaim.model_validate_json(payload)
                    if payload != canonical_bytes(claim):
                        raise ValueError("incomplete install claim is not canonical")
                staging_manifest_path = path / "staging-manifest.json"
                if "staging-manifest.json" in names:
                    _validate_private_file(
                        staging_manifest_path, "incomplete staging manifest"
                    )
                    payload = read_bounded(staging_manifest_path, 128_000)
                    staging_manifest = SkillStagingManifest.model_validate_json(payload)
                    if payload != canonical_bytes(staging_manifest):
                        raise ValueError("incomplete staging manifest is not canonical")
                payload_path = path / "payload"
                if "payload" in names:
                    _validate_private_directory(
                        payload_path, "incomplete install payload"
                    )
                    _directory_inventory(payload_path)
                if intent is not None:
                    if (
                        intent.transaction_id != entry.name
                        or intent.installed_store_policy_sha256
                        != self.policy.policy_sha256
                        or intent.installation_authority_policy_sha256
                        != installation_policy.policy_sha256
                        or intent.claim_store_policy_sha256
                        != self.policy.claim_store_policy_sha256
                        or intent.staging_store_policy_sha256
                        != self.policy.staging_store_policy_sha256
                    ):
                        raise ValueError(
                            "incomplete install intent differs from store policy"
                        )
                    if authorization is not None:
                        decision = authorization.signed_decision.decision
                        if (
                            intent.authorization_sha256
                            != authorization.authorization_sha256
                            or intent.decision_sha256 != decision.decision_sha256
                            or intent.archive_sha256 != decision.archive_sha256
                            or intent.skill != decision.skill
                            or intent.action != decision.action
                            or intent.staging_manifest_sha256
                            != decision.staging_manifest_sha256
                            or intent.control_anchor_entry_sha256
                            != decision.control_anchor_entry_sha256
                            or authorization.installation_target_id
                            != self.policy.store_id
                        ):
                            raise ValueError(
                                "incomplete install authorization differs from intent"
                            )
                    if claim is not None and (
                        intent.claim_sha256 != claim.claim_sha256
                        or intent.authorization_sha256 != claim.authorization_sha256
                        or intent.decision_sha256 != claim.decision_sha256
                        or intent.archive_sha256 != claim.archive_sha256
                        or claim.claim_store_policy_sha256
                        != self.policy.claim_store_policy_sha256
                        or claim.installation_target_id != self.policy.store_id
                    ):
                        raise ValueError("incomplete install claim differs from intent")
                    if staging_manifest is not None and (
                        intent.staging_manifest_sha256
                        != staging_manifest.manifest_sha256
                        or intent.staging_store_policy_sha256
                        != staging_manifest.intent.store_policy_sha256
                        or intent.archive_sha256
                        != staging_manifest.intent.archive_sha256
                        or intent.action != staging_manifest.intent.action
                        or intent.skill != staging_manifest.intent.skill
                    ):
                        raise ValueError(
                            "incomplete staging manifest differs from intent"
                        )
                if "manifest.json" in names:
                    _verify_installed_package(path, self.policy, installation_policy)
                incomplete.append(
                    IncompleteSkillInstallTransaction(
                        transaction_id=entry.name,
                        intent_present=intent is not None,
                        authorization_present="authorization.json" in names,
                        claim_present="claim.json" in names,
                        staging_manifest_present="staging-manifest.json" in names,
                        completion_manifest_present="manifest.json" in names,
                        decision_sha256=(
                            intent.decision_sha256 if intent is not None else None
                        ),
                        archive_sha256=(
                            intent.archive_sha256 if intent is not None else None
                        ),
                    )
                )
        if len(package_names) > self.policy.max_packages:
            raise ValueError("installed package inventory exceeds policy")
        if len(incomplete) > self.policy.max_incomplete_transactions:
            raise ValueError("incomplete install inventory exceeds policy")
        return SkillInstalledStoreSnapshot(
            policy=self.policy,
            packages=tuple(sorted(package_names)),
            incomplete=tuple(sorted(incomplete, key=lambda item: item.transaction_id)),
        )

    def snapshot(
        self,
        installation_policy: SkillInstallationAuthorityPolicy,
    ) -> SkillInstalledStoreSnapshot:
        with self._locked():
            return self._snapshot_unlocked(installation_policy)

    def load(
        self,
        archive_sha256: str,
        installation_policy: SkillInstallationAuthorityPolicy,
    ) -> tuple[
        InstalledSkillManifest,
        SkillPackageArchive,
        AuthenticatedSkillInstallation,
        SkillInstallationClaim,
    ]:
        if re.fullmatch(r"[0-9a-f]{64}", archive_sha256) is None:
            raise ValueError("installed archive digest is invalid")
        with self._locked():
            self._snapshot_unlocked(installation_policy)
            return _verify_installed_package(
                self.packages_path / archive_sha256,
                self.policy,
                installation_policy,
            )

    def preflight_absent(
        self,
        archive_sha256: str,
        installation_policy: SkillInstallationAuthorityPolicy,
    ) -> None:
        with self._locked():
            snapshot = self._snapshot_unlocked(installation_policy)
            if archive_sha256 in snapshot.packages:
                raise ValueError("exact skill package is already installed")
            if len(snapshot.packages) >= self.policy.max_packages:
                raise ValueError("installed package limit reached")
            if len(snapshot.incomplete) >= self.policy.max_incomplete_transactions:
                raise ValueError("incomplete skill install transaction limit reached")

    def _install_under_guard(
        self,
        archive: SkillPackageArchive,
        staging_manifest: SkillStagingManifest,
        authorization: AuthenticatedSkillInstallation,
        claim: SkillInstallationClaim,
        installation_policy: SkillInstallationAuthorityPolicy,
        now: datetime,
    ) -> SkillInstallResult:
        current = _require_utc(now)
        archive = SkillPackageArchive.model_validate_json(canonical_bytes(archive))
        verify_skill_archive(archive)
        decision = authorization.signed_decision.decision
        if (
            self.policy.store_id != authorization.installation_target_id
            or self.policy.installation_authority_policy_sha256
            != installation_policy.policy_sha256
            or self.policy.staging_store_policy_sha256
            != staging_manifest.intent.store_policy_sha256
            or self.policy.claim_store_policy_sha256 != claim.claim_store_policy_sha256
            or claim.authorization_sha256 != authorization.authorization_sha256
            or claim.decision_sha256 != decision.decision_sha256
            or claim.archive_sha256 != archive.archive_sha256
            or decision.staging_manifest_sha256 != staging_manifest.manifest_sha256
            or decision.archive_sha256 != archive.archive_sha256
            or decision.skill != archive.descriptor.identity
            or decision.action != staging_manifest.intent.action
        ):
            raise ValueError("skill installation inputs do not match installed store")
        with self._locked():
            snapshot = self._snapshot_unlocked(installation_policy)
            destination = self.packages_path / archive.archive_sha256
            if destination.exists() or archive.archive_sha256 in snapshot.packages:
                raise ValueError("exact skill package is already installed")
            if len(snapshot.packages) >= self.policy.max_packages:
                raise ValueError("installed package limit reached")
            if len(snapshot.incomplete) >= self.policy.max_incomplete_transactions:
                raise ValueError("incomplete skill install transaction limit reached")
            transaction_id = token_hex(16)
            transaction_path = self.transactions_path / transaction_id
            transaction_path.mkdir(mode=0o700)
            intent = SkillInstallIntent(
                transaction_id=transaction_id,
                installed_store_policy_sha256=self.policy.policy_sha256,
                installation_authority_policy_sha256=installation_policy.policy_sha256,
                authorization_sha256=authorization.authorization_sha256,
                decision_sha256=decision.decision_sha256,
                claim_store_policy_sha256=claim.claim_store_policy_sha256,
                claim_sha256=claim.claim_sha256,
                staging_store_policy_sha256=staging_manifest.intent.store_policy_sha256,
                staging_manifest_sha256=staging_manifest.manifest_sha256,
                control_anchor_entry_sha256=decision.control_anchor_entry_sha256,
                action=decision.action,
                archive_sha256=archive.archive_sha256,
                skill=archive.descriptor.identity,
                started_at=current,
            )
            private_write(transaction_path / "intent.json", canonical_bytes(intent))
            private_write(
                transaction_path / "authorization.json", canonical_bytes(authorization)
            )
            private_write(transaction_path / "claim.json", canonical_bytes(claim))
            private_write(
                transaction_path / "staging-manifest.json",
                canonical_bytes(staging_manifest),
            )
            _fsync_directory(transaction_path)
            _fsync_directory(self.transactions_path)
            payload_root = transaction_path / "payload"
            payload_root.mkdir(mode=0o700)
            installed_files: list[InstalledSkillFile] = []
            for item in archive.files:
                path = payload_root / item.path
                parent = payload_root
                for part in PurePosixPath(item.path).parts[:-1]:
                    parent /= part
                    if not parent.exists():
                        parent.mkdir(mode=0o700)
                private_write(path, item.payload)
                installed_files.append(
                    InstalledSkillFile(
                        path=item.path,
                        content_sha256=item.content_sha256,
                        byte_count=item.byte_count,
                    )
                )
            manifest = InstalledSkillManifest(
                intent=intent,
                descriptor=archive.descriptor,
                files=tuple(installed_files),
                installed_at=current,
            )
            private_write(transaction_path / "manifest.json", canonical_bytes(manifest))
            _verify_installed_package(
                transaction_path,
                self.policy,
                installation_policy,
                archive,
            )
            _fsync_tree_directories(transaction_path)
            _fsync_directory(self.transactions_path)
            os.rename(transaction_path, destination)
            _fsync_directory(self.transactions_path)
            _fsync_directory(self.packages_path)
            return SkillInstallResult(
                manifest=manifest,
                package_path=str(destination),
                claim=claim,
            )


def install_authenticated_skill_release(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    staging_store: SkillStagingStore,
    authorization: AuthenticatedSkillInstallation,
    installation_policy: SkillInstallationAuthorityPolicy,
    claim_store: SkillInstallationClaimStore,
    installed_store: SkillInstalledStore,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> SkillInstallResult:
    """Consume exact authority and atomically install bytes without activating them."""
    current = _require_utc(now)
    if (
        installed_store.policy.installation_authority_policy_sha256
        != installation_policy.policy_sha256
        or installed_store.policy.staging_store_policy_sha256
        != staging_store.policy.policy_sha256
        or installed_store.policy.claim_store_policy_sha256
        != claim_store.policy.policy_sha256
        or installed_store.policy.store_id != authorization.installation_target_id
    ):
        raise ValueError("installed store is not the authorized installation target")
    staging_manifest, selected = staging_store.load(authorization.archive_sha256)
    installed_store.preflight_absent(selected.archive_sha256, installation_policy)
    with guard_and_claim_skill_installation(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        staging_store,
        authorization,
        installation_policy,
        claim_store,
        action,
        current,
    ) as claim:
        return installed_store._install_under_guard(  # pyright: ignore[reportPrivateUsage]
            selected,
            staging_manifest,
            authorization,
            claim,
            installation_policy,
            current,
        )


def inspect_skill_install_recovery(
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    claim_store: SkillInstallationClaimStore,
) -> SkillInstallRecoverySnapshot:
    """Correlate durable claims with completed or incomplete inert installations."""
    installed_snapshot = installed_store.snapshot(installation_policy)
    claim_snapshot = claim_store.snapshot(installation_policy)
    completed: dict[str, tuple[str, str]] = {}
    for archive_sha256 in installed_snapshot.packages:
        manifest, _, authorization, claim = installed_store.load(
            archive_sha256, installation_policy
        )
        completed[claim.decision_sha256] = (
            authorization.authorization_sha256,
            manifest.manifest_sha256,
        )
    incomplete: dict[str, IncompleteSkillInstallTransaction] = {}
    for transaction in installed_snapshot.incomplete:
        if transaction.decision_sha256 is not None:
            if transaction.decision_sha256 in incomplete:
                raise ValueError("one installation decision has multiple transactions")
            incomplete[transaction.decision_sha256] = transaction
    claims_by_decision = {item.decision_sha256: item for item in claim_snapshot.claims}
    if set(completed) & set(incomplete):
        raise ValueError("one installation decision is both complete and incomplete")
    if not set(completed) <= set(claims_by_decision) or not set(incomplete) <= set(
        claims_by_decision
    ):
        raise ValueError("installed state contains a transaction without its claim")
    entries: list[SkillInstallRecoveryEntry] = []
    for decision_sha256, claim in claims_by_decision.items():
        if decision_sha256 in completed:
            authorization_sha256, manifest_sha256 = completed[decision_sha256]
            if authorization_sha256 != claim.authorization_sha256:
                raise ValueError(
                    "completed installation authorization differs from claim"
                )
            entries.append(
                SkillInstallRecoveryEntry(
                    decision_sha256=decision_sha256,
                    authorization_sha256=claim.authorization_sha256,
                    archive_sha256=claim.archive_sha256,
                    state="completed",
                    installed_manifest_sha256=manifest_sha256,
                )
            )
        elif decision_sha256 in incomplete:
            transaction = incomplete[decision_sha256]
            if transaction.archive_sha256 != claim.archive_sha256:
                raise ValueError("incomplete installation archive differs from claim")
            entries.append(
                SkillInstallRecoveryEntry(
                    decision_sha256=decision_sha256,
                    authorization_sha256=claim.authorization_sha256,
                    archive_sha256=claim.archive_sha256,
                    state="incomplete",
                    transaction_id=transaction.transaction_id,
                )
            )
        else:
            entries.append(
                SkillInstallRecoveryEntry(
                    decision_sha256=decision_sha256,
                    authorization_sha256=claim.authorization_sha256,
                    archive_sha256=claim.archive_sha256,
                    state="claim_only",
                )
            )
    return SkillInstallRecoverySnapshot(
        installed_store_policy_sha256=installed_store.policy.policy_sha256,
        claim_store_policy_sha256=claim_store.policy.policy_sha256,
        entries=tuple(sorted(entries, key=lambda item: item.decision_sha256)),
        unbound_transactions=tuple(
            sorted(
                item.transaction_id
                for item in installed_snapshot.incomplete
                if item.decision_sha256 is None
            )
        ),
    )
