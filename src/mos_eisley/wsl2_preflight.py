"""Read-only WSL2 preparation diagnostics; never an execution admission gate."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import stat
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path, PurePosixPath

MAX_METADATA_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Mount:
    point: PurePosixPath
    filesystem: str
    writable: bool


@dataclass(frozen=True)
class DirectoryCheck:
    role: str
    path: str
    mount: str | None
    filesystem: str | None
    issues: tuple[str, ...]


def classify_kernel(system: str, release: str) -> str:
    """Recognize the standard kernel; custom/old kernels remain unqualified."""
    if system != "Linux":
        return "not_wsl"
    lowered = release.lower()
    if "microsoft" in lowered and re.search(r"(?:^|[-_])wsl2(?:$|[-_+.])", lowered):
        return "wsl2_candidate"
    if "microsoft" in lowered:
        return "wsl1_or_unrecognized_wsl"
    return "not_wsl"


def _unescape(value: str) -> str:
    return re.sub(r"\\(040|011|012|134)", lambda match: chr(int(match[1], 8)), value)


def parse_mounts(text: str) -> tuple[Mount, ...]:
    """Parse mountinfo, omitting source names and arbitrary mount option values."""
    mounts: list[Mount] = []
    if len(text.encode()) > MAX_METADATA_BYTES:
        raise ValueError("mount_metadata_too_large")
    for line in text.splitlines():
        fields = line.split()
        try:
            separator = fields.index("-")
            if separator < 6 or len(fields) != separator + 4:
                raise ValueError("invalid_mount_metadata")
            int(fields[0])
            int(fields[1])
            point = _unescape(fields[4])
            if not point.startswith("/"):
                raise ValueError("invalid_mount_metadata")
            options = set(fields[5].split(","))
            super_options = set(fields[separator + 3].split(","))
            mounts.append(
                Mount(
                    PurePosixPath(point),
                    fields[separator + 1],
                    "rw" in options
                    and "ro" not in options
                    and "rw" in super_options
                    and "ro" not in super_options,
                )
            )
        except (ValueError, IndexError) as exc:
            raise ValueError("invalid_mount_metadata") from exc
    if not mounts:
        raise ValueError("missing_mount_metadata")
    return tuple(mounts)


def covering_mount(path: PurePosixPath, mounts: tuple[Mount, ...]) -> Mount | None:
    covered = [mount for mount in mounts if path.is_relative_to(mount.point)]
    if not covered:
        return None
    depth = max(len(mount.point.parts) for mount in covered)
    deepest = [mount for mount in covered if len(mount.point.parts) == depth]
    # Stacked mounts need kernel mount-ID reconciliation, not an order guess.
    return deepest[0] if len(deepest) == 1 else None


def check_directory(
    role: str, path: Path, mounts: tuple[Mount, ...], uid: int, *, private: bool
) -> DirectoryCheck:
    issues: list[str] = []
    try:
        resolved = path.expanduser().resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError):
        return DirectoryCheck(role, str(path), None, None, ("directory_unavailable",))
    if not stat.S_ISDIR(metadata.st_mode):
        issues.append("not_a_directory")
    if private:
        if metadata.st_uid != uid:
            issues.append("private_directory_wrong_owner")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            issues.append("private_directory_not_private")
    mount = covering_mount(PurePosixPath(str(resolved)), mounts)
    if mount is None:
        issues.append("mount_unknown_or_ambiguous")
    else:
        if mount.filesystem != "ext4":
            issues.append("filesystem_not_qualified_candidate")
        if not mount.writable:
            issues.append("mount_read_only")
    return DirectoryCheck(
        role,
        str(resolved),
        str(mount.point) if mount else None,
        mount.filesystem if mount else None,
        tuple(issues),
    )


def read_metadata(path: Path) -> str:
    with path.open("rb") as stream:
        data = stream.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError("os_metadata_too_large")
    return data.decode("utf-8", errors="strict")


def distribution_metadata(text: str) -> dict[str, str]:
    """Keep only distro identity; do not execute shell syntax from os-release."""
    selected: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"ID", "VERSION_ID", "PRETTY_NAME"}:
            selected[key] = value.strip().strip("\"'")[:256]
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    parser.add_argument(
        "--private-dir",
        type=Path,
        action="append",
        default=[],
        help="additional existing memory/config/credential directory (repeatable)",
    )
    arguments = parser.parse_args(argv)
    if len(arguments.private_dir) > 16:
        parser.error("at most 16 additional private directories")
    system = platform.system()
    kernel = platform.release()
    classification = classify_kernel(system, kernel)
    issues: list[str] = []
    if classification != "wsl2_candidate":
        issues.append("recognized_wsl2_kernel_required")
    uid = os.getuid() if hasattr(os, "getuid") else -1
    if uid <= 0:
        issues.append("non_root_posix_user_required")
    try:
        mounts = parse_mounts(read_metadata(Path("/proc/self/mountinfo")))
    except (OSError, UnicodeError, ValueError):
        mounts = ()
        issues.append("mount_metadata_unavailable_or_invalid")
    try:
        distro = distribution_metadata(read_metadata(Path("/etc/os-release")))
    except (OSError, UnicodeError, ValueError):
        distro = {}
    if not distro.get("ID") or not distro.get("VERSION_ID"):
        issues.append("distribution_metadata_unavailable")
    directories = [
        check_directory("workspace", arguments.workspace, mounts, uid, private=False),
        check_directory("storage", arguments.storage, mounts, uid, private=True),
    ]
    for path in arguments.private_dir:
        directories.append(check_directory("private", path, mounts, uid, private=True))
    passed = not issues and all(not item.issues for item in directories)
    report = {
        "schema_version": 1,
        "event": "wsl2.preparation_preflight",
        "preparation_passed": passed,
        "platform_qualified": False,
        "execution_authorized": False,
        "execution_backend": "not_probed",
        "windows_host_evidence": "required_separately",
        "mos_eisley_version": version("mos-eisley"),
        "python": platform.python_version(),
        "system": system,
        "kernel": kernel,
        "architecture": platform.machine(),
        "classification": classification,
        "distribution": distro,
        "issues": issues,
        "directories": [asdict(item) for item in directories],
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
