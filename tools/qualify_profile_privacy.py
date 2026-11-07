"""Provider-free, two-real-UID qualification on disposable GitHub-hosted runners.

Root provisions accounts and observes synthetic fixtures. Every product command
executes as a non-root principal with an empty supplementary-group list. Refuse
local execution; never create accounts on an operator's workstation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import pwd
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from contextlib import suppress
from pathlib import Path

from mos_eisley.app_release import parse_release

VERSION = "0.1.0-rc.16"
SOURCE = "14eb79d52950f340aba159815222e04e6ea864e3"
PINS = {
    "release.json": "1882d3db109ebc3b6f0d5c84de8dec0eecde96a47da5f72ad444d133b30ea3bc",
    "mos_eisley-0.1.0rc16-py3-none-any.whl": (
        "2fef66d8ca749243de89f76170830c7f054f1a15f86bb8d395575529d275a143"
    ),
    "BOOTSTRAP_SHA256SUMS": (
        "9f72ad60c798fcb1143752886888f0d05b0640b2ca196c5f2a1b9f5c4588a20c"
    ),
    "requirements.runtime.txt": (
        "801ecab0fa288ae526cd0eec12e0838d75b5dc947010658862aa36586ff36a85"
    ),
}
LIMIT = 131072


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree(path: Path) -> dict[str, str]:
    return {
        str(p.relative_to(path)): sha(p)
        for p in sorted(path.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


def finish(process: subprocess.Popen[bytes], data: bytes = b"") -> tuple[int, bytes]:
    """Drain both pipes with a total byte bound and kill/reap the entire group."""
    output = bytearray()
    try:
        if process.stdin is not None:
            process.stdin.write(data)
            process.stdin.close()
        with selectors.DefaultSelector() as selected:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    selected.register(stream, selectors.EVENT_READ)
            deadline = time.monotonic() + 120
            while selected.get_map():
                require(time.monotonic() < deadline, "command deadline")
                for key, _ in selected.select(timeout=0.1):
                    block = os.read(key.fd, 8192)
                    if not block:
                        selected.unregister(key.fileobj)
                    else:
                        output.extend(block)
                        require(len(output) <= LIMIT, "command output limit")
        process.wait(timeout=max(0.1, deadline - time.monotonic()))
        return process.returncode, bytes(output)
    finally:
        # Descendants retaining no pipe must not survive the admitted process.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def admin(arguments: list[str]) -> None:
    code, _ = finish(
        subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    )
    require(code == 0, "account administration failed")


def add_user(name: str, home: Path) -> tuple[int, int]:
    try:
        pwd.getpwnam(name)
    except KeyError:
        pass
    else:
        raise ValueError("test account already exists")
    if platform.system() == "Darwin":
        used = {entry.pw_uid for entry in pwd.getpwall()}
        uid = next(value for value in range(610, 900) if value not in used)
        record = "/Users/" + name
        admin(["/usr/bin/dscl", ".", "-create", record])
        for key, value in {
            "UniqueID": str(uid),
            "PrimaryGroupID": "20",
            "UserShell": "/usr/bin/false",
            "NFSHomeDirectory": str(home),
            "IsHidden": "1",
            "AuthenticationAuthority": ";DisabledUser;",
        }.items():
            admin(["/usr/bin/dscl", ".", "-create", record, key, value])
    else:
        admin(
            [
                "/usr/sbin/useradd",
                "--no-create-home",
                "--home-dir",
                str(home),
                "--shell",
                "/usr/sbin/nologin",
                name,
            ]
        )
    entry = pwd.getpwnam(name)
    require(entry.pw_uid > 0, "non-root actor required")
    home.mkdir(mode=0o700)
    os.chown(home, entry.pw_uid, entry.pw_gid)
    return entry.pw_uid, entry.pw_gid


def remove_user(name: str) -> None:
    if platform.system() == "Darwin":
        admin(["/usr/bin/dscl", ".", "-delete", "/Users/" + name])
    else:
        admin(["/usr/sbin/userdel", name])


class Principal:
    def __init__(
        self, home: Path, uid: int, gid: int, python: Path, actor: Path
    ) -> None:
        self.home, self.uid, self.gid, self.python, self.actor = (
            home,
            uid,
            gid,
            python,
            actor,
        )
        self.env = {
            "HOME": str(home),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C.UTF-8" if platform.system() == "Linux" else "en_US.UTF-8",
            "TERM": "dumb",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        for variable, directory in {
            "TMPDIR": "tmp",
            "XDG_CONFIG_HOME": "config",
            "XDG_DATA_HOME": "data",
            "XDG_CACHE_HOME": "cache",
        }.items():
            path = home / directory
            path.mkdir(mode=0o700)
            os.chown(path, uid, gid)
            self.env[variable] = str(path)

    def start(self, arguments: list[str]) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.home,
            env=self.env,
            user=self.uid,
            group=self.gid,
            extra_groups=[],
            umask=0o077,
            start_new_session=True,
            close_fds=True,
        )

    def command(
        self, arguments: list[str], *, data: bytes = b"", success: bool = True
    ) -> bytes:
        code, output = finish(self.start(arguments), data)
        require((code == 0) == success, "unexpected product command status")
        if not success:
            require(
                b"SYNTHETIC-OWNER" not in output and b"fixture boundary" not in output,
                "foreign command disclosed fixture content",
            )
        return output

    def argv(
        self,
        operation: str,
        root: Path,
        backend: str,
        sid: str = "",
        workspace: Path | None = None,
    ) -> list[str]:
        return [
            str(self.python),
            "-I",
            str(self.actor),
            operation,
            str(root),
            backend,
            "--sid",
            sid,
            "--workspace",
            str(workspace or root / "workspace"),
        ]

    def act(
        self,
        operation: str,
        root: Path,
        backend: str,
        sid: str = "",
        workspace: Path | None = None,
    ) -> dict[str, object]:
        receipt = json.loads(
            self.command(self.argv(operation, root, backend, sid, workspace))
        )
        require(
            receipt.get("passed") is True and receipt.get("uid") == self.uid,
            "actor identity or case failed",
        )
        return receipt


def authenticate(assets: Path, target: str) -> tuple[Path, Path]:
    for name, expected in PINS.items():
        require(sha(assets / name) == expected, "public asset enrollment mismatch")
    release = parse_release((assets / "release.json").read_bytes())
    payload = json.loads((assets / "release.json").read_bytes())["payload"]
    require(
        payload["source_commit"] == SOURCE
        and payload["version"] == VERSION
        and payload["storage_epoch"] == 2,
        "candidate identity mismatch",
    )
    require(release.version == VERSION, "signed metadata version mismatch")
    selected = next(a for a in payload["artifacts"] if a["platform"] == target)
    archive = assets / f"mos-{VERSION}-{target}.tar.gz"
    require(
        sha(archive) == selected["sha256"]
        and archive.stat().st_size == selected["size"],
        "signed archive mismatch",
    )
    bootstrap = assets / ("mos-install-" + target)
    require(
        f"{sha(bootstrap)}  {bootstrap.name}"
        in (assets / "BOOTSTRAP_SHA256SUMS").read_text().splitlines(),
        "bootstrap mismatch",
    )
    return archive, bootstrap


def native_cases(
    principal: Principal,
    assets: Path,
    archive: Path,
    bootstrap: Path,
    backend: str,
    foreign: Principal,
    foreign_sid: str,
) -> dict[str, object]:
    home = principal.home
    executable = home / "bin" / "mos"
    if not executable.exists():
        principal.command(
            [
                str(bootstrap),
                "--metadata",
                str(assets / "release.json"),
                "--archive",
                str(archive),
                "--version",
                VERSION,
                "--channel",
                "preview",
                "--root",
                str(home / "app"),
                "--bin-dir",
                str(home / "bin"),
            ]
        )
        require(
            principal.command([str(executable), "--version"]).strip()
            == f"mos-eisley {VERSION}".encode(),
            "installed version mismatch",
        )
        principal.command(
            [str(executable), "update", "disable", "--root", str(home / "app")]
        )
    common = [
        "--storage-backend",
        backend,
        "--storage",
        str(home / ("native-" + backend)),
        "-C",
        str(home / "workspace"),
        "--no-memory",
    ]
    raw = principal.command(
        [
            str(executable),
            "exec",
            "--json",
            *common,
            "Remember that the fixture boundary is ten.",
        ]
    )
    result = next(
        item
        for line in raw.splitlines()
        if line.startswith(b"{")
        and (item := json.loads(line)).get("type") == "exec.result"
    )
    require(result["exit_code"] == 0, "native recorded execution failed")
    sid = result["session_id"]
    resumed = principal.command(
        [str(executable), "resume", sid, "--plain", *common],
        data=b"What boundary did I give you?\n",
    )
    require(b"You gave me a boundary of ten." in resumed, "native cold resume failed")
    before = tree(foreign.home / backend)
    foreign_common = [
        "--storage-backend",
        backend,
        "--storage",
        str(foreign.home / backend),
        "-C",
        str(home / "workspace"),
    ]
    # These are admitted public commands, not parser-error pseudo-successes.
    for arguments in (
        ["sessions", *foreign_common, "--json"],
        ["resume", foreign_sid, *foreign_common, "--plain", "--no-memory"],
        [
            "session-delete",
            foreign_sid,
            *foreign_common,
            "--expected-sha256",
            "0" * 64,
            "--json",
        ],
    ):
        principal.command([str(executable), *arguments], data=b"/quit\n", success=False)
    require(
        tree(foreign.home / backend) == before, "foreign native command mutated state"
    )
    return {
        "recorded_exec": True,
        "cold_resume": True,
        "cross_owner_native_cases": 3,
        "updates": "explicitly disabled for isolated privacy profile",
    }


def qualify(args: argparse.Namespace, report: dict[str, object]) -> None:
    require(os.geteuid() == 0, "root setup required on disposable runner")
    require(
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
        "disposable GitHub-hosted runner required; local account creation forbidden",
    )
    assets = args.assets.resolve()
    target = (
        ("macos" if platform.system() == "Darwin" else "linux")
        + "-"
        + (
            "aarch64"
            if platform.machine().lower() in {"arm64", "aarch64"}
            else "x86_64"
        )
    )
    archive, bootstrap = authenticate(assets, target)
    bootstrap.chmod(0o755)
    report.update(
        target=target,
        system=platform.system(),
        release=platform.release(),
        machine=platform.machine(),
        candidate_source=SOURCE,
        version=VERSION,
        release_sha256=PINS["release.json"],
        harness_sha256=sha(Path(__file__)),
        actor_sha256=sha(args.actor),
        controller_commit=args.commit,
        workflow_run=os.environ.get("GITHUB_RUN_ID"),
        native_archive_sha256=sha(archive),
        provider_calls=0,
        evaluation_eligibility_claim=False,
    )
    if args.host_evidence:
        host = json.loads(args.host_evidence.read_text(encoding="utf-8-sig"))
        require(
            host["host_os"] == "Windows"
            and host["distribution_version"] == 2
            and "microsoft" in platform.release().lower(),
            "actual WSL2 host proof required",
        )
        report["windows_host"] = host
    users: list[str] = []
    with tempfile.TemporaryDirectory(
        prefix="mos-two-real-users-", dir="/tmp"
    ) as temporary:
        base = Path(temporary).resolve()
        base.chmod(0o755)
        try:
            principals = []
            for label in ("a", "b"):
                name = "mosprivacy" + label
                # Register before provisioning so partial creation is cleaned.
                try:
                    pwd.getpwnam(name)
                except KeyError:
                    pass
                else:
                    raise ValueError("preexisting account cannot be used")
                users.append(name)
                home = base / label
                uid, gid = add_user(name, home)
                principals.append(
                    Principal(
                        home, uid, gid, args.python.absolute(), args.actor.resolve()
                    )
                )
            a, b = principals
            require(a.uid != b.uid, "two distinct real users required")
            report["principals"] = [
                {"label": "A", "uid": a.uid},
                {"label": "B", "uid": b.uid},
            ]
            cases: list[dict[str, object]] = []
            report["cases"] = cases
            for backend in ("snapshot", "sqlite"):
                for actor in principals:
                    cases.append(actor.act("seed", actor.home, backend))
                    cases.append(actor.act("owner", actor.home, backend))
                for actor, foreign in ((a, b), (b, a)):
                    sid = json.loads(
                        (foreign.home / (backend + "-session.json")).read_text()
                    )["sid"]
                    before = tree(foreign.home / backend)
                    cases.append(
                        actor.act(
                            "foreign",
                            foreign.home,
                            backend,
                            sid,
                            actor.home / "workspace",
                        )
                    )
                    require(
                        tree(foreign.home / backend) == before,
                        "foreign access mutated owner store",
                    )
                    # Root-controlled copy challenges embedded owner IDs after
                    # kernel permissions permit access. No root tampering claim.
                    copied = actor.home / ("foreign-copy-" + backend)
                    copied.mkdir(mode=0o700)
                    shutil.copytree(foreign.home / backend, copied / backend)
                    shutil.copytree(foreign.home / "memory", copied / "memory")
                    for path in (copied, *copied.rglob("*")):
                        os.chown(path, actor.uid, actor.gid)
                    copied_before = tree(copied)
                    cases.append(
                        actor.act(
                            "foreign", copied, backend, sid, actor.home / "workspace"
                        )
                    )
                    require(
                        tree(copied) == copied_before, "substitution mutated fixture"
                    )
                for actor in principals:
                    sid = json.loads(
                        (actor.home / (backend + "-session.json")).read_text()
                    )["sid"]
                    holder = actor.start(actor.argv("hold", actor.home, backend, sid))
                    try:
                        require(holder.stdout is not None, "lock handshake missing")
                        with selectors.DefaultSelector() as ready:
                            ready.register(holder.stdout, selectors.EVENT_READ)
                            require(
                                bool(ready.select(timeout=30)),
                                "lock handshake deadline",
                            )
                        handshake = json.loads(holder.stdout.readline(LIMIT))
                        require(
                            handshake == {"locked": True, "uid": actor.uid},
                            "lock not held",
                        )
                        cases.append(actor.act("contend", actor.home, backend, sid))
                    finally:
                        code, _ = finish(holder, b"release\n")
                        require(code == 0, "lock holder failed")
                for actor, foreign in ((a, b), (b, a)):
                    sid = json.loads(
                        (foreign.home / (backend + "-session.json")).read_text()
                    )["sid"]
                    cases.append(
                        {
                            "backend": backend,
                            "uid": actor.uid,
                            **native_cases(
                                actor, assets, archive, bootstrap, backend, foreign, sid
                            ),
                        }
                    )
                for actor in principals:
                    sid = json.loads(
                        (actor.home / (backend + "-session.json")).read_text()
                    )["sid"]
                    cases.append(actor.act("erase", actor.home, backend, sid))
            for actor in principals:
                cases.append(actor.act("outbound", actor.home, "snapshot"))
            report["passed"] = True
            report["scope_limits"] = [
                "SDK serialization checked; native-client traffic remains open",
                "default updater traffic is outside explicitly disabled privacy cases",
                "no live auth, billing, containment, inspection or direct-review claim",
                "cache/search/export/migration/auth-rotation checks remain required",
            ]
        finally:
            cleanup = []
            for name in reversed(users):
                try:
                    remove_user(name)
                    cleanup.append(True)
                except Exception:
                    cleanup.append(False)
            report["accounts_removed"] = len(cleanup) == 2 and all(cleanup)
            require(all(cleanup), "account teardown failed")
    report["fixture_tree_removed"] = not base.exists()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--actor", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--host-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report: dict[str, object] = {"schema_version": 1, "passed": False}
    started = time.monotonic()
    try:
        qualify(args, report)
    except Exception as error:
        report.update(passed=False, failure_kind=type(error).__name__)
        # Only our fixed assertion reasons are printable; never exception paths,
        # product output, account records, environment or fixture data.
        if isinstance(error, AssertionError):
            report["failure_reason"] = str(error)
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("passed", "elapsed_seconds")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
