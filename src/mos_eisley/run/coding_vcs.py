"""Host-owned, bounded Git staging for exact approved coding briefs.

Children receive text snapshots and return patches. They never receive this broker,
its staging directory, a Git executable, or the creator's repository authority.
"""

import os
import re
import signal
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock

from mos_eisley.coding_child import (
    CodeFile,
    CodeSnapshot,
    CodingBrief,
    CodingPatch,
    safe_code_path,
)
from mos_eisley.core.models import digest


@dataclass
class _Stage:
    path: Path
    brief_sha256: str
    patch_sha256: str
    base: str
    tree: str
    diff: str
    snapshot: CodeSnapshot
    commit: str | None = None
    consumed: bool = False
    integrated: bool = False


class CodingVCS:
    """A trusted host's explicit stage/integrate capability; no child entry point.

    The workspace and private staging root must be exclusively host-controlled.
    Unexpected state is rejected, and altered/uncertain worktrees are preserved.
    """

    def __init__(self, git: Path, workspace: Path, staging_root: Path) -> None:
        if not git.is_absolute() or not git.is_file():
            raise ValueError("Git must be an explicit absolute executable.")
        self.git = git
        self.workspace = self._directory(workspace)
        if not staging_root.is_absolute() or staging_root.is_symlink():
            raise ValueError("Staging needs an absolute private directory.")
        staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.staging_root = self._directory(staging_root)
        if self.staging_root == self.workspace or self.staging_root.is_relative_to(
            self.workspace
        ):
            raise ValueError("Staging must be outside the creator workspace.")
        if stat.S_IMODE(self.staging_root.stat().st_mode) & 0o077:
            raise ValueError("Staging must be private to its owner.")
        self._stages: dict[str, _Stage] = {}
        self._closed = False
        self._operation_lock = Lock()
        self._operation_deadline: float | None = None
        self._operation_cancelled: Event | None = None
        self._repository(self.workspace)

    @staticmethod
    def _check_operation(deadline: float, cancelled: Event) -> None:
        if cancelled.is_set():
            raise InterruptedError("The owned broker operation was cancelled.")
        if time.monotonic() >= deadline:
            raise TimeoutError("The owned broker operation exceeded its wall bound.")

    def _operation_guard(self) -> None:
        if self._operation_deadline is not None:
            assert self._operation_cancelled is not None
            self._check_operation(self._operation_deadline, self._operation_cancelled)

    def run_operation[T](
        self, operation: Callable[[], T], wall_seconds: int, cancelled: Event
    ) -> T:
        """Run one serialized host operation on an owned worker thread.

        The caller creates the exact cancellation Event before scheduling the
        thread, sets it on cancellation, and awaits that thread's cleanup before
        recording uncertainty. The bound includes lock waiting and every Git
        command. Direct synchronous methods remain trusted host entry points;
        they must not be called concurrently with this operation wrapper.
        """
        if not 1 <= wall_seconds <= 20:
            raise ValueError("Broker operations require a bounded wall allowance.")
        deadline = time.monotonic() + wall_seconds
        while True:
            self._check_operation(deadline, cancelled)
            if self._operation_lock.acquire(timeout=0.01):
                break
        try:
            self._check_operation(deadline, cancelled)
            self._operation_deadline = deadline
            self._operation_cancelled = cancelled
            result = operation()
            self._operation_guard()
            return result
        finally:
            self._operation_deadline = None
            self._operation_cancelled = None
            self._operation_lock.release()

    @staticmethod
    def _directory(path: Path) -> Path:
        if not path.is_absolute() or not path.is_dir() or path.is_symlink():
            raise ValueError("Repository directories must be absolute and regular.")
        if path.resolve() != path:
            raise ValueError("Repository directories must not traverse symlinks.")
        return path

    def _git(self, cwd: Path, *args: str) -> str:
        self._operation_guard()
        # A fresh environment excludes GIT_CONFIG_COUNT, index redirects, object
        # alternates, author overrides, tracing, and all other ambient Git knobs.
        env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
        }
        argv = [str(self.git), "-C", str(cwd)]
        for setting in (
            "core.hooksPath=" + os.devnull,
            "core.fsmonitor=false",
            "core.attributesFile=" + os.devnull,
            "core.autocrlf=false",
            "core.safecrlf=false",
            "core.bare=false",
            "core.worktree=" + str(cwd),
            "core.preloadIndex=false",
            "core.untrackedCache=false",
            "core.splitIndex=false",
            "core.ignoreStat=false",
            "core.checkStat=default",
            "core.symlinks=true",
            "core.ignoreCase=false",
            "core.fileMode=true",
            "core.sparseCheckout=false",
            "protocol.allow=never",
            "diff.external=",
            "diff.renames=false",
            "diff.orderFile=" + os.devnull,
            "diff.context=3",
            "diff.interHunkContext=0",
            "diff.suppressBlankEmpty=false",
            "commit.gpgSign=false",
            "merge.autoStash=false",
            "merge.verifySignatures=false",
            "maintenance.auto=false",
            "gc.auto=0",
            "gc.autoDetach=false",
            "user.name=Mos Eisley Coding Broker",
            "user.email=coding-broker@example.invalid",
            "credential.helper=",
        ):
            argv.extend(("-c", setting))
        argv.extend(args)
        # Spool to private files rather than unbounded PIPE buffers. Enforce the
        # output ceiling while the exact subprocess is running, not after exit.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                process = subprocess.Popen(
                    argv,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=errors,
                    start_new_session=True,
                )
            except OSError as exc:
                raise ValueError("Git could not be started.") from exc
            deadline = time.monotonic() + 10
            try:
                while process.poll() is None:
                    self._operation_guard()
                    if (
                        time.monotonic() >= deadline
                        or output.tell() + errors.tell() > 1_000_000
                    ):
                        raise ValueError("Git exceeded its time or output ceiling.")
                    time.sleep(0.01)
                self._operation_guard()
                if output.tell() + errors.tell() > 1_000_000:
                    raise ValueError("Git exceeded its output ceiling.")
                output.seek(0)
                result = output.read().decode("utf-8")
                if process.returncode:
                    raise ValueError("Git rejected the exact repository operation.")
                return result
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise

    def _repository(self, path: Path) -> None:
        metadata = path / ".git"
        if not metadata.exists() or metadata.is_symlink():
            raise ValueError("Workspace must own exact regular Git metadata.")
        if self._git(path, "rev-parse", "--show-toplevel").strip() != str(path):
            raise ValueError("Workspace is not the exact repository root.")
        # No checkout transformations or local includes are admitted. Reject
        # even inactive filters rather than guessing whether a pattern applies.
        config = self._git(path, "config", "--local", "--no-includes", "--list")
        for line in config.splitlines():
            key = line.partition("=")[0].lower()
            if key.startswith(("filter.", "include.", "includeif.")) or (
                key == "extensions.worktreeconfig"
                and line.partition("=")[2].lower() not in {"false", "no", "0"}
            ):
                raise ValueError("Git filters and local includes are not admitted.")
        common = Path(self._git(path, "rev-parse", "--git-common-dir").strip())
        if not common.is_absolute():
            common = path / common
        if (common / "info" / "grafts").exists() or (
            common / "info" / "grafts"
        ).is_symlink():
            raise ValueError("Repository ancestry overrides are not admitted.")
        attributes = common / "info" / "attributes"
        if (attributes.exists() or attributes.is_symlink()) and (
            attributes.is_symlink() or attributes.stat().st_size
        ):
            raise ValueError("Repository attributes are not admitted.")
        entries = self._git(path, "ls-tree", "-rlz", "HEAD").split("\x00")
        if len(entries) > 4097:
            raise ValueError("Repository exceeds the bounded checkout size.")
        total_size = 0
        for entry in filter(None, entries):
            metadata, name = entry.split("\t", 1)
            mode, kind, _, size = metadata.split()
            if kind != "blob" or not size.isdecimal():
                raise ValueError("Checkout permits only bounded regular blobs.")
            total_size += int(size)
            if int(size) > 2_000_000 or total_size > 32_000_000:
                raise ValueError("Repository exceeds its checkout byte ceiling.")
            if mode not in {
                "100644",
                "100755",
            } or ".gitattributes" in name.lower().split("/"):
                raise ValueError("Checkout requires regular files without attributes.")

    def _index_visible(self, path: Path) -> None:
        flags = self._git(path, "ls-files", "-v").splitlines()
        if any(not line.startswith("H ") for line in flags):
            raise ValueError("Hidden or sparse index entries are not admitted.")

    def _clean(self, path: Path) -> None:
        self._index_visible(path)
        if self._git(
            path, "status", "--porcelain=v1", "--untracked-files=all", "--ignored"
        ):
            raise ValueError("Workspace contains staged, changed or ambient files.")

    @staticmethod
    def _file(root: Path, name: str) -> Path:
        safe_code_path(name)
        path = root / name
        for parent in (path, *path.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError("Coding paths must not follow symlinks.")
        if path.exists() and not path.is_file():
            raise ValueError("Coding paths must be regular files.")
        return path

    def snapshot(self, paths: tuple[str, ...]) -> tuple[str, CodeSnapshot]:
        if self._closed or paths != tuple(sorted(set(paths))):
            raise ValueError("Snapshot paths must be sorted and unique.")
        self._repository(self.workspace)
        self._clean(self.workspace)
        head = self._git(self.workspace, "rev-parse", "HEAD").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            raise ValueError("Coding requires an exact SHA-1 commit identity.")
        files: list[CodeFile] = []
        for name in paths:
            path = self._file(self.workspace, name)
            entry = self._git(self.workspace, "ls-files", "--stage", "--", name)
            if not entry or entry.split(" ", 1)[0] not in {"100644", "100755"}:
                raise ValueError("Snapshots require current tracked regular files.")
            if path.stat().st_size > 64_000:
                raise ValueError("Source exceeds the file ceiling.")
            files.append(CodeFile(path=name, content=path.read_bytes().decode("utf-8")))
        self._clean(self.workspace)
        if head != self._git(self.workspace, "rev-parse", "HEAD").strip():
            raise ValueError("Repository changed during snapshot.")
        return head, CodeSnapshot(files=tuple(files))

    def _parent(self, brief: CodingBrief) -> None:
        if brief.assignment.workspace != str(self.workspace):
            raise ValueError("Assignment belongs to another workspace.")
        head, snapshot = self.snapshot(tuple(f.path for f in brief.snapshot.files))
        if head != brief.base_commit or snapshot != brief.snapshot:
            raise ValueError("Creator repository differs from the approved brief.")
        frozen_paths = {item.path for item in brief.snapshot.files}
        for name in set(brief.owned_paths) - frozen_paths:
            if self._file(self.workspace, name).exists() or self._git(
                self.workspace, "ls-files", "--", name
            ):
                raise ValueError("New owned files must be absent from the exact base.")

    def _target(self, brief: CodingBrief) -> Path:
        path = Path(brief.assignment.worktree or "")
        if not path.is_absolute() or not path.is_relative_to(self.staging_root):
            raise ValueError("Assignment worktree must be beneath the private root.")
        if path == self.staging_root or path.resolve() != path:
            raise ValueError("Assignment worktree must be an exact private child.")
        if path.exists() or path.is_symlink():
            raise ValueError("Assignment worktree already exists or is unowned.")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        return path

    def _diff(self, path: Path) -> str:
        result = self._git(
            path,
            "diff",
            "--cached",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--full-index",
            "--no-renames",
            "--diff-algorithm=myers",
            "--no-indent-heuristic",
            "--src-prefix=a/",
            "--dst-prefix=b/",
        )
        if not result or len(result) > 128_000:
            raise ValueError("Patch diff must be nonempty and bounded.")
        return result

    def stage(self, brief: CodingBrief, patch: CodingPatch) -> str:
        if self._closed or brief.sha256 in self._stages:
            raise ValueError("Coding brief has already been staged or broker closed.")
        target = patch.apply(brief)
        self._parent(brief)
        path = self._target(brief)
        self._git(
            self.workspace, "worktree", "add", "--detach", str(path), brief.base_commit
        )
        # Register immediately, including failures, so cleanup never discovers or
        # deletes arbitrary directories merely because they sit below the root.
        record = _Stage(
            path, brief.sha256, patch.sha256, brief.base_commit, "", "", target
        )
        self._stages[brief.sha256] = record
        self._repository(path)
        self._clean(path)
        for change in patch.changes:
            destination = self._file(path, change.file.path)
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination.write_text(change.file.content, encoding="utf-8", newline="")
        self._git(path, "add", "--", *(change.file.path for change in patch.changes))
        record.tree = self._git(path, "write-tree").strip()
        record.diff = self._diff(path)
        self._validate_stage(record)
        self._parent(brief)
        return record.diff

    def _validate_stage(self, record: _Stage) -> None:
        path = self._directory(record.path)
        common = Path(self._git(path, "rev-parse", "--git-common-dir").strip())
        if not common.is_absolute():
            common = path / common
        original = Path(
            self._git(self.workspace, "rev-parse", "--git-common-dir").strip()
        )
        if not original.is_absolute():
            original = self.workspace / original
        if common.resolve() != original.resolve():
            raise ValueError("Staged checkout no longer belongs to this repository.")
        if self._git(path, "rev-parse", "HEAD").strip() != (
            record.commit or record.base
        ):
            raise ValueError("Staged HEAD changed outside the broker.")
        self._repository(path)
        self._index_visible(path)
        if self._git(path, "write-tree").strip() != record.tree:
            raise ValueError("Staged patch was changed outside the broker.")
        if self._git(path, "diff", "--no-ext-diff", "--no-textconv", "--name-only"):
            raise ValueError("Staged working files differ from their index.")
        if self._git(path, "ls-files", "--others", "--exclude-standard") or self._git(
            path, "ls-files", "--others", "--ignored", "--exclude-standard"
        ):
            raise ValueError("Staged checkout contains ambient files.")
        for item in record.snapshot.files:
            file = self._file(path, item.path)
            if file.read_bytes() != item.content.encode():
                raise ValueError("Staged source or protected tests changed.")
        if record.commit is None and self._diff(path) != record.diff:
            raise ValueError("Staged diff changed outside the broker.")

    def integrate(
        self, brief: CodingBrief, patch: CodingPatch, expected_diff_sha: str
    ) -> str:
        record = self._stages.get(brief.sha256)
        if (
            self._closed
            or record is None
            or record.consumed
            or record.patch_sha256 != patch.sha256
            or record.snapshot != patch.apply(brief)
            or digest(record.diff.encode()) != expected_diff_sha
        ):
            raise ValueError(
                "Integration requires the exact unconsumed staged handoff."
            )
        self._parent(brief)
        self._validate_stage(record)
        # From this point, failed acknowledgements are uncertain, never retried.
        record.consumed = True
        self._git(
            record.path,
            "commit",
            "--no-verify",
            "-m",
            "Integrate approved coding patch",
        )
        record.commit = self._git(record.path, "rev-parse", "HEAD").strip()
        self._validate_stage(record)
        self._parent(brief)
        self._git(self.workspace, "merge", "--ff-only", "--no-edit", record.commit)
        self._clean(self.workspace)
        if self._git(self.workspace, "rev-parse", "HEAD").strip() != record.commit:
            raise ValueError("Integration acknowledgement differs from staged commit.")
        record.integrated = True
        return record.commit

    def integrated_snapshot(
        self, brief: CodingBrief, patch: CodingPatch, commit: str
    ) -> CodeSnapshot:
        """Read the actual integrated tree for independent final verification."""
        record = self._stages.get(brief.sha256)
        expected = patch.apply(brief)
        if (
            self._closed
            or record is None
            or not record.integrated
            or record.commit != commit
            or record.patch_sha256 != patch.sha256
            or record.snapshot != expected
            or brief.assignment.workspace != str(self.workspace)
        ):
            raise ValueError("Final verification requires this exact integrated patch.")
        head, snapshot = self.snapshot(tuple(item.path for item in expected.files))
        if head != commit or snapshot != expected:
            raise ValueError("Integrated repository differs from the approved patch.")
        return snapshot

    def close(self) -> None:
        """Remove only registered, unchanged broker worktrees; preserve uncertainty."""
        self._closed = True
        for record in self._stages.values():
            try:
                if not record.tree or (record.consumed and not record.integrated):
                    continue
                self._validate_stage(record)
                self._git(
                    self.workspace, "worktree", "remove", "--force", str(record.path)
                )
            except (ValueError, OSError, UnicodeError):
                # A stale/modified checkout may contain recoverable work. Never
                # use recursive filesystem deletion or broad worktree pruning.
                continue
