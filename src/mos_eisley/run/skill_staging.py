"""Crash-conservative quarantine staging for authenticated skill release bytes."""

from __future__ import annotations

import os
import re
import stat
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
from mos_eisley.run.skill_release import SkillReleaseEvidence
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAnchorPolicy,
    SkillReleaseControlAuthorityPolicy,
    authenticate_skill_release_control,
    verify_authenticated_skill_release_control,
)
from mos_eisley.run.skills import verify_skill_archive
from mos_eisley.run.store import private_write

UtcTimestamp = Annotated[datetime, Field()]
_TRANSACTION_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_ROOT_ENTRIES = frozenset({"policy.json", "packages", "transactions"})


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class SkillStagingStorePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_quarantine_staging_policy"] = "skill_quarantine_staging_policy"
    store_id: Digest
    control_anchor_policy_sha256: Digest
    max_packages: Annotated[int, Field(ge=1, le=10_000)] = 1000
    max_incomplete_transactions: Annotated[int, Field(ge=1, le=1000)] = 100
    installation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class StagedSkillFile(Contract):
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
            raise ValueError("staged skill path is invalid")
        return self


class SkillStagingIntent(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_quarantine_staging_intent"] = "skill_quarantine_staging_intent"
    transaction_id: Identifier
    store_policy_sha256: Digest
    control_anchor_entry_sha256: Digest
    control_receipt_sha256: Digest
    release_evidence_sha256: Digest
    control_sequence: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
    action: Literal["candidate", "rollback"]
    archive_sha256: Digest
    skill: SkillIdentity
    started_at: UtcTimestamp
    installation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("started_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @property
    def intent_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillStagingManifest(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["staged_skill_quarantine_package"] = "staged_skill_quarantine_package"
    intent: SkillStagingIntent
    descriptor: SkillDescriptor
    files: Annotated[tuple[StagedSkillFile, ...], Field(min_length=1, max_length=64)]
    staged_at: UtcTimestamp
    quarantine_staged: Literal[True] = True
    installation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("staged_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_package(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if tuple(sorted(set(paths))) != paths:
            raise ValueError("staged skill files must be unique and sorted")
        if (
            self.intent.skill != self.descriptor.identity
            or self.descriptor.file_count != len(self.files)
            or self.descriptor.package_bytes
            != sum(item.byte_count for item in self.files)
            or self.staged_at < self.intent.started_at
        ):
            raise ValueError("staged skill manifest does not match its intent")
        return self

    @property
    def manifest_sha256(self) -> str:
        return digest(canonical_bytes(self))


class IncompleteSkillStagingTransaction(Contract):
    transaction_id: Identifier
    intent_present: bool
    completion_manifest_present: bool


class SkillStagingStoreSnapshot(Contract):
    schema_version: Literal[1] = 1
    policy: SkillStagingStorePolicy
    packages: Annotated[tuple[Digest, ...], Field(max_length=10_000)]
    incomplete: Annotated[
        tuple[IncompleteSkillStagingTransaction, ...], Field(max_length=1000)
    ]

    @model_validator(mode="after")
    def canonical_inventory(self) -> Self:
        if tuple(sorted(set(self.packages))) != self.packages:
            raise ValueError("staged package inventory must be unique and sorted")
        transaction_ids = tuple(item.transaction_id for item in self.incomplete)
        if tuple(sorted(set(transaction_ids))) != transaction_ids:
            raise ValueError("incomplete transactions must be unique and sorted")
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillStagingResult(Contract):
    schema_version: Literal[1] = 1
    manifest: SkillStagingManifest
    package_path: Annotated[str, Field(min_length=1, max_length=4096)]
    already_present: bool
    installation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False


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


def _fsync_tree_directories(root: Path) -> None:
    directories = [
        root / relative
        for relative, is_directory in _directory_inventory(root)
        if is_directory
    ]
    for path in reversed(directories):
        _fsync_directory(path)
    _fsync_directory(root)


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
                raise ValueError("staged package cannot contain symlinks")
            if stat.S_ISDIR(metadata.st_mode):
                _validate_private_directory(child_path, "staged package directory")
                entries.append((relative, True))
                visit(child_path, (*prefix, child.name))
            elif stat.S_ISREG(metadata.st_mode):
                _validate_private_file(child_path, "staged package file")
                entries.append((relative, False))
            else:
                raise ValueError("staged package contains a special file")
            if len(entries) > 256:
                raise ValueError("staged package inventory exceeds its limit")

    visit(root, ())
    return tuple(entries)


def _expected_inventory(manifest: SkillStagingManifest) -> tuple[tuple[str, bool], ...]:
    directories = {"payload"}
    for item in manifest.files:
        parts = PurePosixPath(item.path).parts[:-1]
        for index in range(1, len(parts) + 1):
            directories.add(PurePosixPath("payload", *parts[:index]).as_posix())
    files = {"intent.json", "manifest.json"} | {
        PurePosixPath("payload", item.path).as_posix() for item in manifest.files
    }
    return tuple(
        sorted(
            (
                *((item, True) for item in directories),
                *((item, False) for item in files),
            )
        )
    )


def _verify_package_path(
    path: Path,
    expected_archive: SkillPackageArchive | None = None,
) -> tuple[SkillStagingManifest, SkillPackageArchive]:
    _validate_private_directory(path, "staged package")
    manifest_path = path / "manifest.json"
    intent_path = path / "intent.json"
    _validate_private_file(manifest_path, "staged package manifest")
    _validate_private_file(intent_path, "staged package intent")
    manifest = SkillStagingManifest.model_validate_json(
        read_bounded(manifest_path, 128_000)
    )
    if read_bounded(intent_path, 128_000) != canonical_bytes(manifest.intent):
        raise ValueError("staged package intent differs from completion manifest")
    if _directory_inventory(path) != _expected_inventory(manifest):
        raise ValueError("staged package inventory differs from completion manifest")
    archived_files: list[ArchivedSkillFile] = []
    for item in manifest.files:
        payload_path = path / "payload" / item.path
        payload = read_bounded(payload_path, item.byte_count)
        if len(payload) != item.byte_count or digest(payload) != item.content_sha256:
            raise ValueError("staged package file differs from completion manifest")
        archived_files.append(ArchivedSkillFile.retain(item.path, payload))
    archive = SkillPackageArchive(
        descriptor=manifest.descriptor,
        files=tuple(archived_files),
    )
    verify_skill_archive(archive)
    if archive.archive_sha256 != manifest.intent.archive_sha256:
        raise ValueError("staged package archive digest differs from its intent")
    if expected_archive is not None and archive != expected_archive:
        raise ValueError("staged package differs from selected release archive")
    return manifest, archive


class SkillStagingStore:
    """Content-addressed quarantine store disconnected from runtime configuration."""

    def __init__(self, root: Path):
        self.root = root.absolute()
        self._validate_layout()
        policy_path = self.root / "policy.json"
        _validate_private_file(policy_path, "skill staging policy")
        payload = read_bounded(policy_path, 64_000)
        self.policy = SkillStagingStorePolicy.model_validate_json(payload)
        if payload != canonical_bytes(self.policy):
            raise ValueError("skill staging policy is not canonical")

    @classmethod
    def create(
        cls,
        root: Path,
        policy: SkillStagingStorePolicy,
        anchor_policy: SkillReleaseControlAnchorPolicy,
    ) -> SkillStagingStore:
        policy = SkillStagingStorePolicy.model_validate_json(canonical_bytes(policy))
        anchor_policy = SkillReleaseControlAnchorPolicy.model_validate_json(
            canonical_bytes(anchor_policy)
        )
        if policy.control_anchor_policy_sha256 != anchor_policy.policy_sha256:
            raise ValueError("skill staging policy does not match control anchor")
        root.mkdir(mode=0o700)
        private_write(root / "policy.json", canonical_bytes(policy))
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
        _validate_private_directory(self.root, "skill staging store")
        if {item.name for item in os.scandir(self.root)} != set(_ROOT_ENTRIES):
            raise ValueError("skill staging store root inventory is invalid")
        _validate_private_directory(
            self.root / "packages", "skill staging packages directory"
        )
        _validate_private_directory(
            self.root / "transactions", "skill staging transactions directory"
        )

    def snapshot(self) -> SkillStagingStoreSnapshot:
        self._validate_layout()
        package_names: list[str] = []
        with os.scandir(self.packages_path) as package_entries:
            for entry in package_entries:
                if not re.fullmatch(r"[0-9a-f]{64}", entry.name):
                    raise ValueError("skill staging package name is invalid")
                _, archive = _verify_package_path(Path(entry.path))
                if archive.archive_sha256 != entry.name:
                    raise ValueError("skill staging package path digest is invalid")
                package_names.append(entry.name)
        incomplete: list[IncompleteSkillStagingTransaction] = []
        with os.scandir(self.transactions_path) as transaction_entries:
            for entry in transaction_entries:
                if _TRANSACTION_PATTERN.fullmatch(entry.name) is None:
                    raise ValueError("skill staging transaction name is invalid")
                path = Path(entry.path)
                _validate_private_directory(path, "incomplete staging transaction")
                names = {item.name for item in os.scandir(path)}
                incomplete.append(
                    IncompleteSkillStagingTransaction(
                        transaction_id=entry.name,
                        intent_present="intent.json" in names,
                        completion_manifest_present="manifest.json" in names,
                    )
                )
        if len(package_names) > self.policy.max_packages:
            raise ValueError("skill staging package inventory exceeds policy")
        if len(incomplete) > self.policy.max_incomplete_transactions:
            raise ValueError("incomplete skill staging inventory exceeds policy")
        return SkillStagingStoreSnapshot(
            policy=self.policy,
            packages=tuple(sorted(package_names)),
            incomplete=tuple(sorted(incomplete, key=lambda item: item.transaction_id)),
        )

    def load(
        self, archive_sha256: str
    ) -> tuple[SkillStagingManifest, SkillPackageArchive]:
        if re.fullmatch(r"[0-9a-f]{64}", archive_sha256) is None:
            raise ValueError("skill staging archive digest is invalid")
        self.snapshot()
        return _verify_package_path(self.packages_path / archive_sha256)

    def stage(
        self,
        archive: SkillPackageArchive,
        control: AuthenticatedSkillReleaseControl,
        anchor_entry_sha256: str,
        action: Literal["candidate", "rollback"],
        now: datetime,
    ) -> SkillStagingResult:
        current = _require_utc(now)
        archive = SkillPackageArchive.model_validate_json(canonical_bytes(archive))
        control = AuthenticatedSkillReleaseControl.model_validate_json(
            canonical_bytes(control)
        )
        verify_skill_archive(archive)
        if action == "candidate":
            if (
                not control.release_allowed
                or archive.archive_sha256 != control.archive_sha256
            ):
                raise ValueError("candidate staging requires an allowed exact release")
        elif (
            not control.release_revoked
            or control.rollback_archive is None
            or archive != control.rollback_archive
        ):
            raise ValueError("rollback staging requires exact nominated rollback bytes")
        snapshot = self.snapshot()
        destination = self.packages_path / archive.archive_sha256
        if destination.exists():
            manifest, _ = _verify_package_path(destination, archive)
            return SkillStagingResult(
                manifest=manifest,
                package_path=str(destination),
                already_present=True,
            )
        if len(snapshot.packages) >= self.policy.max_packages:
            raise ValueError("skill staging package limit reached")
        if len(snapshot.incomplete) >= self.policy.max_incomplete_transactions:
            raise ValueError("incomplete skill staging transaction limit reached")
        transaction_id = token_hex(16)
        transaction_path = self.transactions_path / transaction_id
        transaction_path.mkdir(mode=0o700)
        intent = SkillStagingIntent(
            transaction_id=transaction_id,
            store_policy_sha256=self.policy.policy_sha256,
            control_anchor_entry_sha256=anchor_entry_sha256,
            control_receipt_sha256=control.control_receipt_sha256,
            release_evidence_sha256=control.release_evidence_sha256,
            control_sequence=control.signed_control.decision.sequence,
            action=action,
            archive_sha256=archive.archive_sha256,
            skill=archive.descriptor.identity,
            started_at=current,
        )
        private_write(transaction_path / "intent.json", canonical_bytes(intent))
        _fsync_directory(transaction_path)
        _fsync_directory(self.transactions_path)
        payload_root = transaction_path / "payload"
        payload_root.mkdir(mode=0o700)
        staged_files: list[StagedSkillFile] = []
        for item in archive.files:
            path = payload_root / item.path
            parents = PurePosixPath(item.path).parts[:-1]
            parent = payload_root
            for part in parents:
                parent /= part
                if not parent.exists():
                    parent.mkdir(mode=0o700)
            private_write(path, item.payload)
            staged_files.append(
                StagedSkillFile(
                    path=item.path,
                    content_sha256=item.content_sha256,
                    byte_count=item.byte_count,
                )
            )
        manifest = SkillStagingManifest(
            intent=intent,
            descriptor=archive.descriptor,
            files=tuple(staged_files),
            staged_at=current,
        )
        private_write(transaction_path / "manifest.json", canonical_bytes(manifest))
        _verify_package_path(transaction_path, archive)
        _fsync_tree_directories(transaction_path)
        _fsync_directory(self.transactions_path)
        os.rename(transaction_path, destination)
        _fsync_directory(self.transactions_path)
        _fsync_directory(self.packages_path)
        return SkillStagingResult(
            manifest=manifest,
            package_path=str(destination),
            already_present=False,
        )


def stage_authenticated_skill_release(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_authority_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    authenticated_control: AuthenticatedSkillReleaseControl,
    control_authority_policy: SkillReleaseControlAuthorityPolicy,
    control_anchor: SkillReleaseControlAnchor,
    staging_store: SkillStagingStore,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> SkillStagingResult:
    """Reverify every source and stage only the exact latest controlled bytes."""

    current = _require_utc(now)
    verify_authenticated_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authority_policy,
        archive,
        evidence,
        authenticated_control,
        control_authority_policy,
    )
    current_control = authenticate_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authority_policy,
        archive,
        evidence,
        authenticated_control.signed_control,
        control_authority_policy,
        authenticated_control.rollback_archive,
        current,
    )
    if (
        staging_store.policy.control_anchor_policy_sha256
        != control_anchor.policy.policy_sha256
    ):
        raise ValueError("skill staging store does not match release control anchor")
    selected = archive if action == "candidate" else current_control.rollback_archive
    if selected is None:
        raise ValueError("skill release control has no rollback archive")
    with control_anchor.guard_latest(
        current_control,
        control_authority_policy,
        current,
    ) as anchored:
        return staging_store.stage(
            selected,
            current_control,
            anchored.anchor_entry_sha256,
            action,
            current,
        )
