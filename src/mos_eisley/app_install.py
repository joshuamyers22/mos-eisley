"""User-owned transactional application installation; session stores stay separate."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from collections.abc import Generator
from pathlib import Path, PurePosixPath

from mos_eisley.app_release import (
    MAX_EXPANDED,
    STORAGE_EPOCH,
    Release,
    ReleaseError,
    platform_id,
    verify_archive,
    version_key,
)


def default_root() -> Path:
    return Path.home() / ".local/share/mos-eisley-app"


def private_root(root: Path) -> None:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Every installation root is owner-controlled; refuse shared/writable roots.
    info = root.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ReleaseError(
            "installation root must be an owned private directory (0700)"
        )
    for parent in root.parents:
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX
        ):
            raise ReleaseError("installation path has an unsafe ancestor")


def atomic_json(path: Path, value: object) -> None:
    fd, name = tempfile.mkstemp(prefix=".metadata-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def lock(root: Path, *, shared: bool = False) -> Generator[None]:
    private_root(root)
    descriptor = os.open(
        root / "clients.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ReleaseError("unsafe installation lock")
        try:
            fcntl.flock(
                descriptor, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB
            )
        except BlockingIOError as error:
            raise ReleaseError(
                "another client is active; finish work and close sessions "
                "before updating"
            ) from error
        yield
    finally:
        os.close(descriptor)


def _link(root: Path, name: str) -> str | None:
    path = root / name
    if not path.is_symlink():
        if path.exists():
            raise ReleaseError(f"unsafe {name} pointer")
        return None
    value = os.readlink(path)
    if not value.startswith("releases/") or PurePosixPath(value).parts != (
        "releases",
        PurePosixPath(value).name,
    ):
        raise ReleaseError("unsafe release pointer")
    return value


def activate_pointer(root: Path, name: str, value: str) -> None:
    pending = root / f".{name}-next"
    pending.unlink(missing_ok=True)
    pending.symlink_to(value)
    os.replace(pending, root / name)
    sync_directory(root)


def installed_release(root: Path) -> Release | None:
    from mos_eisley.app_release import parse_release

    current = _link(root, "current")
    if current is None:
        return None
    directory = root / current
    if directory.is_symlink() or not directory.is_dir():
        raise ReleaseError("installed release directory is unsafe")
    return parse_release((directory / "release.json").read_bytes())


def extract_archive(raw: bytes, destination: Path) -> None:
    total = 0
    seen: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for count, member in enumerate(archive):
            name = PurePosixPath(member.name)
            if (
                count >= 30000
                or len(member.name) > 400
                or name.is_absolute()
                or ".." in name.parts
                or not name.parts
                or member.name in seen
                or "\\" in member.name
                or not (member.isfile() or member.isdir())
            ):
                raise ReleaseError("unsafe archive member")
            if str(name) != member.name.rstrip("/") or any(
                part in ("", ".") for part in name.parts
            ):
                raise ReleaseError("noncanonical archive path")
            seen.add(member.name)
            total += member.size
            if member.size < 0 or total > MAX_EXPANDED:
                raise ReleaseError("expanded archive exceeds limit")
            target = destination.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            else:
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ReleaseError("archive file missing")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                target.chmod(0o700 if member.mode & 0o111 else 0o600)
    if not (destination / "mos").is_file():
        raise ReleaseError("archive has no mos launcher")


def record_runtime(directory: Path) -> None:
    values = {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }
    atomic_json(directory / "runtime-files.json", values)


def verify_runtime(directory: Path) -> None:
    values = json.loads((directory / "runtime-files.json").read_text())
    if not isinstance(values, dict) or not values:
        raise ReleaseError("invalid runtime integrity inventory")
    actual = {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file() and path.name != "runtime-files.json"
    }
    if actual != values or any(path.is_symlink() for path in directory.rglob("*")):
        raise ReleaseError("installed runtime is damaged; reinstall or roll back")


def verify_binary(directory: Path, version: str) -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OPENAI_", "ANTHROPIC_", "PYTHON", "MOS_"))
    }
    result = subprocess.run(
        [str(directory / "mos"), "--version"],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != f"mos-eisley {version}":
        raise ReleaseError("staged runtime version verification failed")


def _launcher(root: Path, bin_dir: Path) -> Path:
    bin_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = bin_dir.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o022
    ):
        raise ReleaseError("launcher directory is not owner-controlled")
    path = bin_dir / "mos"
    expected = str(root / "current/mos")
    if path.is_symlink():
        if os.readlink(path) != expected:
            raise ReleaseError(
                "another installation owns this mos launcher; choose another --bin-dir"
            )
    elif path.exists():
        raise ReleaseError("another command owns mos; choose another --bin-dir")
    return path


def install(
    root: Path,
    bin_dir: Path,
    release: Release,
    raw: bytes,
    *,
    origin: str = "standalone",
) -> None:
    root = root.absolute()
    bin_dir = bin_dir.absolute()
    with lock(root):
        launcher = _launcher(root, bin_dir)
        current = installed_release(root)
        if current is not None and version_key(release.version) < version_key(
            current.version
        ):
            raise ReleaseError("downgrades require compatible explicit rollback")
        if (
            current is not None
            and current.version == release.version
            and current.raw != release.raw
        ):
            raise ReleaseError("immutable release metadata changed")
        artifact = release.artifact(platform_id())
        verify_archive(raw, artifact)
        versions = root / "releases"
        versions.mkdir(mode=0o700, exist_ok=True)
        if versions.is_symlink():
            raise ReleaseError("unsafe release storage")
        name = f"{release.version}-{artifact.platform}"
        target = versions / name
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
        try:
            extract_archive(raw, stage)
            with (stage / "release.json").open("xb") as metadata:
                metadata.write(release.raw)
                metadata.flush()
                os.fsync(metadata.fileno())
            record_runtime(stage)
            verify_binary(stage, release.version)
            if target.exists():
                if (
                    target.is_symlink()
                    or (target / "release.json").read_bytes() != release.raw
                ):
                    raise ReleaseError("existing immutable installation conflicts")
                verify_runtime(target)
                verify_binary(target, release.version)
            else:
                sync_directory(stage)
                os.replace(stage, target)
                sync_directory(versions)
            old = _link(root, "current")
            new = f"releases/{name}"
            atomic_json(
                root / "transaction.json",
                {"schema": 1, "old": old, "new": new, "storage_epoch": STORAGE_EPOCH},
            )
            if old is not None and old != new:
                activate_pointer(root, "previous", old)
            # Metadata must be durable before the activation commit point.
            atomic_json(
                root / "install.json",
                {
                    "schema": 1,
                    "origin": origin,
                    "bin_dir": str(bin_dir),
                    "storage_epoch": STORAGE_EPOCH,
                },
            )
            activate_pointer(root, "current", new)
            if not launcher.is_symlink():
                launcher.symlink_to(str(root / "current/mos"))
                sync_directory(bin_dir)
            (root / "transaction.json").unlink()
            sync_directory(root)
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def recover(root: Path) -> str:
    """Validate the committed pointer; leave all user state and evidence untouched."""
    with lock(root):
        current = installed_release(root)
        if current is None:
            raise ReleaseError("no committed runtime; rerun the pinned installer")
        pointer = _link(root, "current")
        assert pointer is not None
        verify_runtime(root / pointer)
        verify_binary(root / pointer, current.version)
        (root / "transaction.json").unlink(missing_ok=True)
        sync_directory(root)
        return current.version


def rollback(root: Path) -> str:
    from mos_eisley.app_release import parse_release

    with lock(root):
        previous = _link(root, "previous")
        current = installed_release(root)
        if previous is None or current is None:
            raise ReleaseError("no compatible previous installation")
        release = parse_release((root / previous / "release.json").read_bytes())
        if release.storage_epoch != current.storage_epoch:
            raise ReleaseError("rollback storage compatibility is unproven")
        verify_runtime(root / previous)
        verify_binary(root / previous, release.version)
        activate_pointer(root, "current", previous)
        return release.version


def uninstall(root: Path) -> None:
    with lock(root):
        metadata = json.loads((root / "install.json").read_text())
        launcher = Path(metadata["bin_dir"]) / "mos"
        if launcher.is_symlink() and os.readlink(launcher) == str(root / "current/mos"):
            launcher.unlink()
        # Remove only our managed runtime directories, never shared application data.
        for name in ("current", "previous"):
            _link(root, name)
            (root / name).unlink(missing_ok=True)
        shutil.rmtree(root / "releases")
        for name in ("install.json", "transaction.json"):
            (root / name).unlink(missing_ok=True)
