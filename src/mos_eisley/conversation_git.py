"""Read-only, bounded Git inventory and path admission for a selected workspace.

This module does not render a panel or authorize prompt attachments. Git output is
untrusted data, and every returned path is relative to the selected directory.
"""

import hashlib
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from mos_eisley.conversation_directory import DirectorySelection
from mos_eisley.run.process import bounded_process

MAX_INVENTORY_BYTES = 1_000_000
MAX_PATCH_BYTES = 256_000
MAX_FILES = 512
MAX_PATH_BYTES = 4096
MAX_CONFIG_BYTES = 128_000
MAX_HELPER_OVERRIDES = 64
GIT_DEADLINE_SECONDS = 5


class GitReadError(ValueError):
    """A safe, fixed message for a failed or stale read."""


class GitState(StrEnum):
    READY = "ready"
    UNBORN = "unborn"
    NON_GIT = "non_git"


class ChangeKind(StrEnum):
    TRACKED = "tracked"
    UNTRACKED = "untracked"


class DiffBasis(StrEnum):
    STAGED = "staged"
    UNSTAGED = "unstaged"


@dataclass(frozen=True)
class Change:
    path: str
    kind: ChangeKind
    staged: str | None = None
    unstaged: str | None = None
    old_path: str | None = None
    staged_added: int | None = None
    staged_removed: int | None = None
    unstaged_added: int | None = None
    unstaged_removed: int | None = None


@dataclass(frozen=True)
class GitSnapshot:
    state: GitState
    workspace: Path
    root: Path | None
    changes: tuple[Change, ...]
    digest: str
    complete: bool
    omission: str | None = None


@dataclass(frozen=True)
class Patch:
    path: str
    basis: DiffBasis
    snapshot_digest: str
    data: bytes
    digest: str


def _admit_path(raw: bytes, prefix: str) -> str | None:
    try:
        path = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    if (
        not path
        or len(raw) > MAX_PATH_BYTES
        or not path.isprintable()
        or "\\" in path
        or path.startswith("/")
    ):
        return None
    parts = PurePosixPath(path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    if str(PurePosixPath(*parts)) != path:
        return None
    if prefix:
        if not path.startswith(prefix + "/"):
            return None
        return path[len(prefix) + 1 :]
    return path


def _numstat(
    data: bytes, prefix: str
) -> tuple[dict[str, tuple[int | None, int | None]], int]:
    if data and not data.endswith(b"\0"):
        raise GitReadError("Git returned an incomplete change inventory.")
    fields = data.split(b"\0") if data else []
    result: dict[str, tuple[int | None, int | None]] = {}
    omitted = 0
    index = 0
    while index < len(fields) - 1:
        head = fields[index]
        index += 1
        parts = head.split(b"\t", 2)
        if len(parts) != 3:
            raise GitReadError("Git returned an invalid change inventory.")
        raw_path = parts[2]
        if not raw_path:
            if index + 1 >= len(fields) - 1:
                raise GitReadError("Git returned an incomplete change inventory.")
            old_path = _admit_path(fields[index], prefix)
            raw_path = fields[index + 1]
            index += 2
            if old_path is None:
                omitted += 1
                continue
        path = _admit_path(raw_path, prefix)
        if path is None:
            omitted += 1
            continue
        try:
            counts = tuple(None if value == b"-" else int(value) for value in parts[:2])
        except ValueError:
            raise GitReadError("Git returned an invalid change inventory.") from None
        if any(
            value is not None and (value < 0 or value > 1_000_000_000)
            for value in counts
        ):
            raise GitReadError("Git returned an invalid change inventory.")
        result[path] = (counts[0], counts[1])
    return result, omitted


def _status(data: bytes, prefix: str) -> tuple[list[Change], int]:
    if data and not data.endswith(b"\0"):
        raise GitReadError("Git returned an incomplete change inventory.")
    fields = data.split(b"\0") if data else []
    changes: list[Change] = []
    omitted = 0
    index = 0
    while index < len(fields) - 1:
        entry = fields[index]
        index += 1
        if len(entry) < 4 or entry[2:3] != b" ":
            raise GitReadError("Git returned an invalid change inventory.")
        code = entry[:2].decode("ascii", errors="replace")
        path = _admit_path(entry[3:], prefix)
        old_path = None
        if "R" in code or "C" in code:
            if index >= len(fields) - 1:
                raise GitReadError("Git returned an incomplete change inventory.")
            old_path = _admit_path(fields[index], prefix)
            index += 1
        if path is None or (old_path is None and ("R" in code or "C" in code)):
            omitted += 1
            continue
        if code == "!!":
            continue
        if code == "??":
            changes.append(Change(path, ChangeKind.UNTRACKED))
        elif all(letter in " MADRCUT?!" for letter in code):
            changes.append(
                Change(
                    path,
                    ChangeKind.TRACKED,
                    staged=code[0] if code[0] != " " else None,
                    unstaged=code[1] if code[1] != " " else None,
                    old_path=old_path,
                )
            )
        else:
            raise GitReadError("Git returned an invalid change inventory.")
        if len(changes) > MAX_FILES:
            raise GitReadError("Git change inventory exceeds the file limit.")
    return changes, omitted


class GitWorkspaceReader:
    """Bind one selected directory to a Git checkout for bounded read operations."""

    def __init__(self, selection: DirectorySelection, git_executable: Path) -> None:
        if not git_executable.is_absolute():
            raise GitReadError("Choose an absolute trusted Git executable.")
        try:
            executable = git_executable.resolve(strict=True)
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise OSError("Git executable unavailable")
        except (OSError, RuntimeError):
            raise GitReadError("The trusted Git executable is unavailable.") from None
        self.selection = selection
        self.git = executable
        self.git_identity = self._git_identity()
        self.root: DirectorySelection | None = None
        self.git_dir: DirectorySelection | None = None
        self.prefix = ""
        selection.verify()
        try:
            root_text = self._scalar(["rev-parse", "--show-toplevel"])
            git_dir_text = self._scalar(["rev-parse", "--absolute-git-dir"])
        except GitReadError:
            # A malformed checkout is a read failure, not an ordinary non-Git
            # directory. Do not turn a resource failure into a clean empty view.
            for parent in (selection.path, *selection.path.parents):
                if (parent / ".git").exists() or (parent / ".git").is_symlink():
                    raise
            return
        try:
            root = DirectorySelection.inspect(Path(root_text))
            git_dir = DirectorySelection.inspect(Path(git_dir_text))
            prefix = selection.path.relative_to(root.path).as_posix()
        except (ValueError, OSError):
            raise GitReadError(
                "Git workspace is outside the selected checkout."
            ) from None
        self.root = root
        self.git_dir = git_dir
        self.prefix = "" if prefix == "." else prefix
        self._verify()

    def _command(self, arguments: list[str], *, limit: int) -> bytes:
        command = [
            str(self.git),
            "--no-pager",
            "--no-replace-objects",
            "--literal-pathspecs",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "core.attributesfile=/dev/null",
            "-c",
            "diff.external=",
            "-c",
            "diff.trustExitCode=false",
            "-c",
            "diff.renameLimit=100",
        ]
        if arguments[0] in {"status", "diff"}:
            for key in self._helper_config_keys():
                command.extend(("-c", f"{key}="))
        command.extend(arguments)
        try:
            return bounded_process(
                command,
                timeout=GIT_DEADLINE_SECONDS,
                limit=limit,
                environment={
                    "LC_ALL": "C",
                    "LANG": "C",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_NO_LAZY_FETCH": "1",
                    "GIT_PAGER": "cat",
                    "GIT_ATTR_NOSYSTEM": "1",
                },
                cwd=self.root.path if self.root is not None else self.selection.path,
            )
        except (OSError, ValueError):
            raise GitReadError(
                "Git read failed or exceeded its resource limit."
            ) from None

    def _helper_config_keys(self) -> tuple[str, ...]:
        """Override configured file transformers before porcelain reads."""
        data = self._config_bytes()
        if data and not data.endswith(b"\0"):
            raise GitReadError("Git configuration is incomplete.")
        keys: set[str] = set()
        for item in data.split(b"\0"):
            if not item:
                continue
            raw_key, separator, _ = item.partition(b"\n")
            if not separator:
                raise GitReadError("Git configuration is invalid.")
            try:
                key = raw_key.decode("ascii")
            except UnicodeDecodeError:
                raise GitReadError("Git configuration is invalid.") from None
            if (
                key.startswith("filter.")
                and key.endswith((".clean", ".smudge", ".process"))
                or key.startswith("diff.")
                and key.endswith((".command", ".textconv"))
            ):
                if len(key) > 256 or not all(
                    character.isalnum() or character in ".-_" for character in key
                ):
                    raise GitReadError("Git helper configuration is unsafe.")
                keys.add(key)
                if len(keys) > MAX_HELPER_OVERRIDES:
                    raise GitReadError("Git helper configuration exceeds its limit.")
        return tuple(sorted(keys))

    def _config_bytes(self) -> bytes:
        return self._command(
            ["config", "--list", "-z", "--includes"], limit=MAX_CONFIG_BYTES
        )

    def _scalar(self, arguments: list[str]) -> str:
        try:
            value = self._command(arguments, limit=MAX_PATH_BYTES).decode("utf-8")
        except UnicodeDecodeError:
            raise GitReadError("Git returned invalid workspace metadata.") from None
        value = value.removesuffix("\n")
        if not value or not value.isprintable():
            raise GitReadError("Git returned invalid workspace metadata.")
        return value

    def _verify(self) -> None:
        try:
            self.selection.verify()
            if self._git_identity() != self.git_identity:
                raise GitReadError("Trusted Git executable changed; select it again.")
            if self.root is not None and self.git_dir is not None:
                self.root.verify()
                self.git_dir.verify()
                if self._scalar(["rev-parse", "--show-toplevel"]) != str(
                    self.root.path
                ):
                    raise GitReadError("Git workspace changed; select it again.")
                if self._scalar(["rev-parse", "--absolute-git-dir"]) != str(
                    self.git_dir.path
                ):
                    raise GitReadError("Git workspace changed; select it again.")
        except ValueError:
            raise GitReadError("Git workspace changed; select it again.") from None

    def _git_identity(self) -> tuple[int, int, int, int]:
        try:
            info = self.git.stat(follow_symlinks=False)
        except OSError:
            raise GitReadError("The trusted Git executable is unavailable.") from None
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    def _pathspec(self) -> list[str]:
        return ["--", self.prefix] if self.prefix else ["--"]

    def _file_stamp(self, path: str) -> bytes:
        """Collect change metadata without following workspace path symlinks."""
        try:
            fd = os.open(
                self.selection.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
        except OSError:
            return b"unsafe-or-unavailable"
        try:
            parts = PurePosixPath(path).parts
            for component in parts[:-1]:
                try:
                    child = os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=fd,
                    )
                except FileNotFoundError:
                    return b"missing"
                os.close(fd)
                fd = child
            try:
                info = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return b"missing"
            return (
                f"{info.st_dev}:{info.st_ino}:{info.st_mode}:{info.st_size}:"
                f"{info.st_mtime_ns}:{info.st_ctime_ns}"
            ).encode("ascii")
        except OSError:
            return b"unsafe-or-unavailable"
        finally:
            os.close(fd)

    def snapshot(self) -> GitSnapshot:
        self._verify()
        if self.root is None:
            return GitSnapshot(
                GitState.NON_GIT,
                self.selection.path,
                None,
                (),
                "",
                True,
            )
        scope = self._pathspec()
        config_before = self._config_bytes()
        head_before = self._head()
        status = self._command(
            [
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--renames",
                "--ignore-submodules=dirty",
                *scope,
            ],
            limit=MAX_INVENTORY_BYTES,
        )
        staged = self._command(
            [
                "diff",
                "--cached",
                "--numstat",
                "-z",
                "--no-ext-diff",
                "--no-textconv",
                "--submodule=short",
                "--ignore-submodules=dirty",
                "--find-renames=50%",
                "-l100",
                *scope,
            ],
            limit=MAX_INVENTORY_BYTES,
        )
        unstaged = self._command(
            [
                "diff",
                "--numstat",
                "-z",
                "--no-ext-diff",
                "--no-textconv",
                "--submodule=short",
                "--ignore-submodules=dirty",
                "--find-renames=50%",
                "-l100",
                *scope,
            ],
            limit=MAX_INVENTORY_BYTES,
        )
        staged_objects = self._command(
            [
                "diff",
                "--cached",
                "--raw",
                "-z",
                "--no-ext-diff",
                "--no-textconv",
                "--submodule=short",
                "--ignore-submodules=dirty",
                "--find-renames=50%",
                "-l100",
                *scope,
            ],
            limit=MAX_INVENTORY_BYTES,
        )
        entries, omitted = _status(status, self.prefix)
        staged_counts, staged_omitted = _numstat(staged, self.prefix)
        unstaged_counts, unstaged_omitted = _numstat(unstaged, self.prefix)
        omitted += staged_omitted + unstaged_omitted
        changes = tuple(
            Change(
                entry.path,
                entry.kind,
                entry.staged,
                entry.unstaged,
                entry.old_path,
                *(staged_counts.get(entry.path, (None, None))),
                *(unstaged_counts.get(entry.path, (None, None))),
            )
            for entry in entries
        )
        stamped = [(entry.path, self._file_stamp(entry.path)) for entry in changes]
        if any(stamp == b"unsafe-or-unavailable" for _, stamp in stamped):
            raise GitReadError("Git workspace paths changed or became unsafe.")
        stamps = b"\0".join(
            path.encode("utf-8") + b"=" + stamp for path, stamp in stamped
        )
        digest = hashlib.sha256(
            b"\0".join(
                (
                    config_before,
                    head_before.encode("ascii"),
                    status,
                    staged,
                    unstaged,
                    staged_objects,
                    stamps,
                )
            )
        ).hexdigest()
        if config_before != self._config_bytes():
            raise GitReadError("Git configuration changed during the read; refresh.")
        if head_before != self._head():
            raise GitReadError("Git HEAD changed during the read; refresh.")
        state = GitState.UNBORN if head_before == "unborn" else GitState.READY
        self._verify()
        return GitSnapshot(
            state,
            self.selection.path,
            self.root.path,
            changes,
            digest,
            omitted == 0,
            f"{omitted} unsafe or out-of-scope entries omitted" if omitted else None,
        )

    def _head(self) -> str:
        try:
            value = self._scalar(["rev-parse", "--verify", "HEAD"])
        except GitReadError:
            try:
                ref = self._scalar(["symbolic-ref", "-q", "HEAD"])
            except GitReadError:
                raise GitReadError("Git HEAD is unavailable.") from None
            if not ref.startswith("refs/heads/"):
                raise GitReadError("Git HEAD is unavailable.") from None
            return "unborn"
        if len(value) not in {40, 64} or not all(
            character in "0123456789abcdef" for character in value
        ):
            raise GitReadError("Git returned invalid HEAD metadata.")
        return value

    def patch(self, snapshot: GitSnapshot, path: str, basis: DiffBasis) -> Patch:
        try:
            basis = DiffBasis(basis)
        except ValueError:
            raise GitReadError("Choose a staged or unstaged comparison.") from None
        self._verify()
        if snapshot != self.snapshot():
            raise GitReadError("Git snapshot changed; refresh before opening a diff.")
        entry = next(
            (change for change in snapshot.changes if change.path == path), None
        )
        if entry is None or entry.kind is not ChangeKind.TRACKED:
            raise GitReadError("The selected tracked path is unavailable.")
        if basis is DiffBasis.STAGED and entry.staged is None:
            raise GitReadError("The selected staged diff is unavailable.")
        if basis is DiffBasis.UNSTAGED and entry.unstaged is None:
            raise GitReadError("The selected unstaged diff is unavailable.")
        repo_path = f"{self.prefix}/{path}" if self.prefix else path
        old_repo_path = (
            (f"{self.prefix}/{entry.old_path}" if self.prefix else entry.old_path)
            if entry.old_path is not None
            else None
        )
        arguments = ["diff"]
        if basis is DiffBasis.STAGED:
            arguments.append("--cached")
        arguments.extend(
            [
                "--no-ext-diff",
                "--no-textconv",
                "--submodule=short",
                "--ignore-submodules=dirty",
                "--no-color",
                "--find-renames=50%",
                "-l100",
                "--",
                repo_path,
            ]
        )
        if old_repo_path is not None:
            arguments.append(old_repo_path)
        data = self._command(arguments, limit=MAX_PATCH_BYTES)
        if snapshot != self.snapshot():
            raise GitReadError("Git snapshot changed while reading the diff.")
        return Patch(
            path, basis, snapshot.digest, data, hashlib.sha256(data).hexdigest()
        )
