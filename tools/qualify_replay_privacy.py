"""Provider-free signed private replay qualification under two actual OS users."""

import argparse
import json
import os
import platform
import pwd
import shutil
import sys
import tempfile
from pathlib import Path

from qualify_profile_privacy import (
    Principal,
    add_user,
    finish,
    remove_user,
    require,
    sha,
    tree,
)


def replay_cases(a: Principal, b: Principal) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for owner, foreign in ((a, b), (b, a)):
        owner.report["replay_owner_uid"] = owner.uid
        owner.report["replay_stage"] = "owner-positive"
        executable = str(owner.home / "bin" / "mos")
        other_executable = str(foreign.home / "bin" / "mos")
        for arguments in (["/usr/bin/id", "-u"], ["/usr/bin/id", "-ru"]):
            require(
                owner.command(arguments).strip() == str(owner.uid).encode(),
                "real/effective principal mismatch",
            )
        code, output = finish(
            owner.start(
                [executable, "demo", "--json", "--output", str(owner.home / "runs")]
            )
        )
        require(code == 1, "recorded demo must return its expected revise verdict")
        event = json.loads(output.splitlines()[0])
        require(
            event.get("type") == "run.saved" and event.get("mode") == "recorded",
            "recorded fixture was not completed",
        )
        runs = [p for p in (owner.home / "runs").iterdir() if p.is_dir()]
        require(len(runs) == 1, "ambiguous synthetic run")
        run = runs[0]
        before = tree(run)
        positive = owner.command([executable, "replay", str(run)])
        require(b'"type": "replay.verified"' in positive, "owner replay missing")
        owner.command(
            [executable, "replay", str(run)]
        )  # Fresh process; no consumed state.
        owner.report["replay_stage"] = "foreign-private"
        private = foreign.command([other_executable, "replay", str(run)], success=False)
        # Keep the original owner's filesystem UID on this readable copy.
        readable = foreign.home / "readable-foreign"
        shutil.copytree(run, readable)
        for path in (readable, *readable.rglob("*")):
            path.chmod(0o755 if path.is_dir() else 0o644)
            os.chown(path, owner.uid, owner.gid)
        copied_before = tree(readable)
        owner.report["replay_stage"] = "foreign-readable"
        refused = foreign.command(
            [other_executable, "replay", str(readable)], success=False
        )
        require(
            foreign.report["last_exit_code"] == 2
            and b"input or artifact validation failed" in refused
            and b"replay.verified" not in private + refused,
            "foreign replay was not refused by validation",
        )
        require(
            tree(readable) == copied_before and tree(run) == before,
            "replay wrote state",
        )
        # A private reader-owned root must also refuse one foreign-owned artifact.
        owner.report["replay_stage"] = "mixed-owner-setup"
        mixed = foreign.home / "mixed-owner"
        shutil.copytree(run, mixed)
        for path in (mixed, *mixed.rglob("*")):
            foreign_artifact = path == mixed / "brief.json"
            path.chmod(
                0o644 if foreign_artifact else (0o700 if path.is_dir() else 0o600)
            )
            principal = owner if foreign_artifact else foreign
            os.chown(path, principal.uid, principal.gid)
        mixed_before = tree(mixed)
        owner.report["replay_stage"] = "foreign-artifact"
        output = foreign.command(
            [other_executable, "replay", str(mixed)], success=False
        )
        require(
            foreign.report["last_exit_code"] == 2
            and b"input or artifact validation failed" in output
            and b"replay.verified" not in output,
            "foreign artifact was not refused by validation",
        )
        require(tree(mixed) == mixed_before, "foreign artifact refusal wrote state")
        cases.append(
            {
                "owner_uid": owner.uid,
                "foreign_uid": foreign.uid,
                "owner_replay": True,
                "fresh_process_replay": True,
                "private_foreign_refused": True,
                "readable_foreign_refused": True,
                "mixed_owner_artifact_refused": True,
                "fixture_bytes_unchanged": True,
            }
        )
    return cases


def qualify(args: argparse.Namespace, report: dict[str, object]) -> None:
    require(os.getuid() == os.geteuid() == 0, "root setup required")
    require(
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
        "local account creation forbidden",
    )
    # Source dependencies already installed by trusted CI. Candidate admission is
    # signed metadata, exact expected version/source, archive and bootstrap pins.
    from mos_eisley.app_release import MAX_METADATA, parse_release, platform_id

    assets = args.assets.resolve()
    with (assets / "release.json").open("rb") as stream:
        raw = stream.read(MAX_METADATA + 1)
    require(len(raw) <= MAX_METADATA, "oversized signed metadata")
    release = parse_release(raw)
    require(
        release.version == args.expected_version
        and release.source_commit == args.expected_source,
        "signed candidate identity mismatch",
    )
    target = platform_id()
    artifact = release.artifact(target)
    archive = assets / f"mos-{release.version}-{target}.tar.gz"
    require(
        archive.stat().st_size == artifact.size and sha(archive) == artifact.sha256,
        "signed archive mismatch",
    )
    bootstrap = assets / ("mos-install-" + target)
    require(
        f"{sha(bootstrap)}  {bootstrap.name}"
        in (assets / "BOOTSTRAP_SHA256SUMS").read_text().splitlines(),
        "bootstrap enrollment mismatch",
    )
    report.update(
        schema_version=1,
        platform=target,
        host_release=platform.release(),
        source_commit=release.source_commit,
        version=release.version,
        metadata_sha256=sha(assets / "release.json"),
        archive_sha256=artifact.sha256,
        controller_sha256=sha(Path(__file__)),
        workflow_run=os.environ.get("GITHUB_RUN_ID"),
        provider_calls=0,
        evaluation_eligibility_claim=False,
    )
    users: list[str] = []
    with tempfile.TemporaryDirectory(
        prefix="mos-replay-privacy-", dir="/tmp"
    ) as temporary:
        base = Path(temporary).resolve()
        base.chmod(0o755)
        shared = base / "assets"
        shared.mkdir(mode=0o755)
        for original in (archive, bootstrap, assets / "release.json"):
            staged = shared / original.name
            shutil.copyfile(original, staged)
            staged.chmod(0o755 if original == bootstrap else 0o644)
            require(sha(staged) == sha(original), "staged asset changed")
        try:
            actors: list[Principal] = []
            for label in ("a", "b"):
                name = "mosreplay" + label
                try:
                    pwd.getpwnam(name)
                except KeyError:
                    pass
                else:
                    raise ValueError("preexisting account cannot be used")
                users.append(name)
                home = base / label
                uid, gid = add_user(name, home)
                actor = Principal(
                    home, uid, gid, Path(sys.executable), Path(__file__), report
                )
                actors.append(actor)
                actor.command(
                    [
                        str(shared / bootstrap.name),
                        "--metadata",
                        str(shared / "release.json"),
                        "--archive",
                        str(shared / archive.name),
                        "--version",
                        release.version,
                        "--channel",
                        release.channel,
                        "--root",
                        str(home / "app"),
                        "--bin-dir",
                        str(home / "bin"),
                    ]
                )
                executable = str(home / "bin" / "mos")
                require(
                    actor.command([executable, "--version"]).strip()
                    == f"mos-eisley {release.version}".encode(),
                    "installed candidate version mismatch",
                )
                actor.command(
                    [executable, "update", "disable", "--root", str(home / "app")]
                )
            require(actors[0].uid != actors[1].uid, "two distinct real users required")
            report["cases"] = replay_cases(*actors)
            report["passed"] = True
        finally:
            cleanup: list[bool] = []
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
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    report: dict[str, object] = {"passed": False, "provider_calls": 0}
    try:
        qualify(args, report)
    except Exception as error:
        report["failure_kind"] = type(error).__name__
        if isinstance(error, AssertionError):
            report["failure_reason"] = str(error)
        return 1
    finally:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
