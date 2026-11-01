"""Exercise actual installed Claude failure receipts using offline shell fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from mos_eisley.app_release import parse_release, platform_id, verify_archive
from mos_eisley.providers.native_progress import NativeProgressReceipt

MARKER = "offline-private-native-text"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(
    executable: Path, base: Path, environment: dict[str, str]
) -> dict[str, object]:
    workspace, clients, attempts = (
        base / n for n in ("workspace", "clients", "attempts")
    )
    for directory in (workspace, clients, attempts):
        directory.mkdir(mode=0o700)
    bodies = {
        "silent": "exec /bin/sleep 30\n",
        "output_wait": (
            f"printf '%s' '{MARKER}'; printf '%s' '{MARKER}' >&2\nexec /bin/sleep 30\n"
        ),
        "exit_wait": "exec 1>&- 2>&-\nexec /bin/sleep 30\n",
        "inherited_pipe": "/bin/sh -c 'trap \"\" TERM; exec /bin/sleep 30' &\nexit 0\n",
    }
    results: dict[str, object] = {}
    for name, body in bodies.items():
        client, attempt = clients / name, attempts / name
        dispatch = clients / f"{name}.dispatch"
        client.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = --version ]; then '
            "printf '%s\\n' '2.1.283 (Claude Code)'; exit 0; fi\n"
            "if [ \"$1\" = auth ]; then printf '%s\\n' "
            '\'{"loggedIn":true,"authMethod":"claude.ai",'
            '"apiProvider":"firstParty"}\'; exit 0; fi\n'
            f"printf x >> {shlex.quote(str(dispatch))}\n"
            "/bin/cat > /dev/null\n" + body
        )
        client.chmod(0o700)
        command = [
            str(executable),
            "subscription",
            "ask",
            "--provider",
            "anthropic_subscription",
            "--client",
            str(client),
            "--model",
            "claude-sonnet-5",
            "--effort",
            "high",
            "--attempt",
            str(attempt),
            "--allow-data-transfer",
            "--allow-subscription-usage",
            "--timeout",
            "2",
            "--max-output-bytes",
            "1000",
            "--json",
        ]
        outcome = subprocess.run(
            command,
            input=MARKER,
            capture_output=True,
            text=True,
            cwd=workspace,
            env=environment,
            timeout=45,
        )
        if outcome.returncode != 2:
            raise ValueError("offline diagnostic did not refuse the stalled fixture")
        raw = (attempt / "failure.json").read_bytes()
        if MARKER.encode() in raw or str(client).encode() in raw or len(raw) >= 1024:
            raise ValueError("native failure diagnostics exposed fixture content")
        failure = json.loads(raw)
        if (
            set(failure)
            != {
                "phase",
                "billing_verified",
                "process_reason",
                "deadline_seconds",
                "elapsed_ms",
                "progress",
            }
            or failure["billing_verified"] is not False
            or failure["deadline_seconds"] != 2
        ):
            raise ValueError("offline failure receipt shape differs")
        if (
            failure["phase"] != "native_process"
            or failure["process_reason"] != "deadline"
        ):
            raise ValueError("offline native failure reason differs")
        progress = NativeProgressReceipt.model_validate(failure["progress"])
        if not progress.stdin_drained or not progress.cleanup_completed:
            raise ValueError("offline exchange or cleanup did not finish correctly")
        if name == "silent" and (
            progress.stdout.bytes_observed or progress.stderr.bytes_observed
        ):
            raise ValueError("silent fixture manufactured output observations")
        if name == "output_wait" and (
            progress.stdout.bytes_observed != len(MARKER)
            or progress.stderr.bytes_observed != len(MARKER)
            or progress.stdout.first_read_ms is None
        ):
            raise ValueError("offline output read counters differ")
        expected_exit = name == "inherited_pipe"
        if progress.leader_exited_before_cleanup is not expected_exit:
            raise ValueError("pre-cleanup leader observation differs")
        if name == "exit_wait":
            if (
                progress.phase != "exit"
                or not progress.stdout.eof
                or not progress.stderr.eof
            ):
                raise ValueError("EOF/exit wait observations differ")
        elif progress.phase != "output" or progress.stdout.eof or progress.stderr.eof:
            raise ValueError("open-pipe observations differ")
        if (attempt / "completion.json").exists() or dispatch.read_bytes() != b"x":
            raise ValueError("offline failure acquired completion or repeated dispatch")
        retry = subprocess.run(
            command,
            input=MARKER,
            capture_output=True,
            text=True,
            cwd=workspace,
            env=environment,
            timeout=45,
        )
        if (
            retry.returncode != 2
            or dispatch.read_bytes() != b"x"
            or (attempt / "failure.json").read_bytes() != raw
        ):
            raise ValueError("failed native attempt was replayed or repaired")
        results[name] = {
            "progress": progress.model_dump(mode="json"),
            "replay_refused": True,
        }
    return results


def qualify(artifacts: Path, evidence: Path, source: str, version: str) -> None:
    metadata = artifacts / "release.json"
    release = parse_release(metadata.read_bytes())
    if (release.source_commit, release.version, release.storage_epoch) != (
        source,
        version,
        2,
    ):
        raise ValueError("signed progress candidate identity differs")
    target = platform_id()
    archive = artifacts / f"mos-{version}-{target}.tar.gz"
    verify_archive(archive.read_bytes(), release.artifact(target))
    bootstrap = artifacts / f"mos-install-{target}"
    if bootstrap.is_symlink() or not bootstrap.is_file():
        raise ValueError("unsafe or missing progress bootstrap")
    if (
        f"{sha(bootstrap)}  {bootstrap.name}"
        not in (artifacts / "BOOTSTRAP_SHA256SUMS").read_text().splitlines()
    ):
        raise ValueError("progress bootstrap checksum differs")
    env = {k: v for k, v in os.environ.items() if k in {"TMPDIR", "LANG", "LC_ALL"}}
    env.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin", TERM="xterm-256color")
    with tempfile.TemporaryDirectory(prefix="mos-signed-progress-") as temporary:
        base = Path(temporary).resolve()
        home = base / "home"
        home.mkdir(mode=0o700)
        env["HOME"] = str(home)
        path = base / "path"
        path.mkdir(mode=0o700)
        env["PATH"] = str(path)
        if any(
            shutil.which(name, path=env["PATH"])
            for name in ("python", "python3", "node")
        ):
            raise ValueError("offline native child PATH exposes a host interpreter")
        bootstrap.chmod(0o700)
        subprocess.run(
            [
                str(bootstrap),
                "--metadata",
                str(metadata),
                "--archive",
                str(archive),
                "--version",
                version,
                "--channel",
                "preview",
                "--root",
                str(base / "app"),
                "--bin-dir",
                str(base / "bin"),
            ],
            env=env,
            cwd=base,
            check=True,
            capture_output=True,
            timeout=90,
        )
        executable = base / "bin/mos"
        subprocess.run(
            [str(executable), "update", "disable", "--root", str(base / "app")],
            env=env,
            cwd=base,
            check=True,
            capture_output=True,
            timeout=30,
        )
        observed = subprocess.check_output(
            [str(executable), "--version"], env=env, text=True, timeout=30
        ).strip()
        if observed != f"mos-eisley {version}":
            raise ValueError("installed progress version differs")
        native_sha = sha(executable.resolve())
        results = probe(executable, base, env)
        subprocess.run(
            [
                str(executable),
                "update",
                "uninstall",
                "--yes",
                "--root",
                str(base / "app"),
            ],
            env=env,
            check=True,
            capture_output=True,
            timeout=45,
        )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": 1,
        "status": "passed",
        "source_commit": source,
        "version": version,
        "platform": target,
        "metadata_sha256": sha(metadata),
        "archive_sha256": sha(archive),
        "bootstrap_sha256": sha(bootstrap),
        "native_sha256": native_sha,
        "harness_sha256": sha(Path(__file__)),
        "publisher": "enrolled_production_root_unpatched",
        "host_python_node_on_path": False,
        "paid_calls": 0,
        "synthetic_dispatches": 4,
        "private_fixture_home": True,
        "cases": results,
        "publication_authorized": False,
    }
    with evidence.open("x") as stream:
        json.dump(report, stream, sort_keys=True)
    print(f"PASS {target}: signed offline native progress and replay refusal")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    qualify(
        args.artifacts.resolve(),
        args.evidence.resolve(),
        args.expected_source,
        args.expected_version,
    )
