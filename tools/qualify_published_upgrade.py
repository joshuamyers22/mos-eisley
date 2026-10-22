"""Qualify untouched publisher-signed predecessor/candidate native artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from mos_eisley import app_install
from mos_eisley.app_release import (
    Release,
    ReleaseError,
    parse_release,
    platform_id,
    verify_archive,
    version_key,
)

PREDECESSOR_VERSION = "0.1.0-rc.1"
PREDECESSOR_COMMIT = "8cf38c83591e505a9c7b57f4d701b12cb80fc4c6"
PUBLISHED_PREDECESSORS = {
    PREDECESSOR_VERSION: PREDECESSOR_COMMIT,
    "0.1.0-rc.2": "ef6a66fc8911902cef7a91828b4b26e7d329020c",
    "0.1.0-rc.3": "b3f04b46fb2091e861bdf3fc5e900d933cf804b3",
    "0.1.0-rc.5": "b04906553f2622210adc82c43893777a6b98aa44",
}


def snapshot(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def artifact(directory: Path, expected_commit: str) -> tuple[Release, bytes, Path]:
    release = parse_release((directory / "release.json").read_bytes())
    if release.source_commit != expected_commit:
        raise ValueError("signed artifact has a different source commit")
    archive = directory / f"mos-{release.version}-{platform_id()}.tar.gz"
    raw = archive.read_bytes()
    verify_archive(raw, release.artifact(platform_id()))
    bootstrap = directory / f"mos-install-{platform_id()}"
    if bootstrap.is_symlink() or not bootstrap.is_file():
        raise ValueError("unsafe or missing native bootstrap")
    return release, raw, bootstrap.resolve()


def published_predecessor(directory: Path, version: str) -> tuple[Release, bytes, Path]:
    commit = PUBLISHED_PREDECESSORS.get(version)
    if commit is None:
        raise ValueError("unsupported published predecessor")
    result = artifact(directory, commit)
    if result[0].version != version:
        raise ValueError("signed predecessor version differs from published selection")
    return result


def interrupt_install(
    root: Path, bin_dir: Path, release: Release, raw: bytes, *, after: bool
) -> None:
    original = app_install.activate_pointer

    def activate(path: Path, name: str, value: str) -> None:
        if name == "current" and not after:
            raise InterruptedError("qualification interruption before activation")
        original(path, name, value)
        if name == "current":
            raise InterruptedError("qualification interruption after activation")

    with patch.object(app_install, "activate_pointer", activate):
        try:
            app_install.install(root, bin_dir, release, raw)
        except InterruptedError:
            pass
        else:
            raise ValueError("interrupted installation unexpectedly completed")
    if not (root / "transaction.json").is_file():
        raise ValueError("interruption did not retain its transaction")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor", type=Path, required=True)
    parser.add_argument(
        "--predecessor-version",
        choices=tuple(PUBLISHED_PREDECESSORS),
        default=PREDECESSOR_VERSION,
    )
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    previous, previous_raw, previous_bootstrap = published_predecessor(
        args.predecessor, args.predecessor_version
    )
    candidate, raw, bootstrap = artifact(args.candidate, args.candidate_commit)
    if version_key(candidate.version) <= version_key(previous.version):
        raise ValueError("candidate must be newer than the published predecessor")
    manifest = (args.predecessor / "BOOTSTRAP_SHA256SUMS").read_text().splitlines()
    expected_bootstrap = hashlib.sha256(previous_bootstrap.read_bytes()).hexdigest()
    if f"{expected_bootstrap}  {previous_bootstrap.name}" not in manifest:
        raise ValueError("published predecessor bootstrap checksum mismatch")

    with tempfile.TemporaryDirectory(prefix="mos-published-upgrade-") as temporary:
        base = Path(temporary).resolve()
        root, bin_dir = base / "app with spaces", base / "bin with spaces"
        workspace = base / "workspace"
        workspace.mkdir()
        environment = {
            name: value
            for name, value in os.environ.items()
            if name in {"TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT"}
        }
        environment.update(HOME=str(base), PATH="/nonexistent")

        def run(executable: Path, *arguments: str, input_text: str = "") -> str:
            result = subprocess.run(
                [str(executable), *arguments],
                env=environment,
                input=input_text,
                text=True,
                capture_output=True,
                timeout=90,
                check=True,
            )
            return result.stdout

        executable = bin_dir / "mos"

        def install_native(directory: Path, release: Release, installer: Path) -> None:
            run(
                installer,
                "--metadata",
                str((directory / "release.json").resolve()),
                "--archive",
                str(
                    (
                        directory / f"mos-{release.version}-{platform_id()}.tar.gz"
                    ).resolve()
                ),
                "--root",
                str(root),
                "--bin-dir",
                str(bin_dir),
                "--version",
                release.version,
                "--channel",
                release.channel,
            )
            run(executable, "update", "disable", "--root", str(root))

        def version(expected: str) -> None:
            if run(executable, "--version").strip() != f"mos-eisley {expected}":
                raise ValueError("active frozen runtime version mismatch")

        install_native(args.predecessor, previous, previous_bootstrap)
        version(previous.version)
        setup = json.loads(run(executable, "setup", "--json"))
        if setup["credentials_required_to_install"] or any(setup["providers"].values()):
            raise ValueError("published setup did not remain credential-free")
        cassette = base / "recorded.json"
        run(executable, "conversation-demo", "--output", str(cassette))
        protected = base / "protected user state"
        protected.mkdir(mode=0o700)
        for name in ("credential-sentinel", "config-sentinel", "spending-sentinel"):
            (protected / name).write_text(f"inert qualification {name}\n")
        protected_before = snapshot(protected)
        stores = {
            backend: base / f"sessions-{backend}" for backend in ("snapshot", "sqlite")
        }

        def session_arguments(backend: str) -> list[str]:
            return [
                "--plain",
                "--no-memory",
                "--storage-backend",
                backend,
                "--storage",
                str(stores[backend]),
                "-C",
                str(workspace),
            ]

        for backend in stores:
            answer = run(
                executable,
                "chat",
                *session_arguments(backend),
                "--cassette",
                str(cassette),
                input_text="Remember that the fixture boundary is ten.\n",
            )
            if "The fixture boundary is ten." not in answer or not snapshot(
                stores[backend]
            ):
                raise ValueError(
                    "published runtime did not save its recorded conversation"
                )

        def saved() -> dict[str, dict[str, str]]:
            return {backend: snapshot(store) for backend, store in stores.items()}

        def preserved(before: dict[str, dict[str, str]]) -> None:
            if saved() != before or snapshot(protected) != protected_before:
                raise ValueError("lifecycle operation changed retained user state")

        def resume() -> None:
            for backend in stores:
                answer = run(
                    executable, "resume", "--last", *session_arguments(backend)
                )
                if "The fixture boundary is ten." not in answer:
                    raise ValueError("cold resume lost the predecessor's saved context")

        resume()
        before = saved()
        install_native(args.candidate, candidate, bootstrap)
        version(candidate.version)
        preserved(before)
        resume()
        before = saved()
        run(executable, "update", "rollback", "--yes", "--root", str(root))
        version(previous.version)
        preserved(before)
        resume()

        # The predecessor must also read a session explicitly advanced by the candidate.
        install_native(args.candidate, candidate, bootstrap)
        for backend in stores:
            answer = run(
                executable,
                "resume",
                "--last",
                *session_arguments(backend),
                input_text="What boundary did I give you?\n",
            )
            if "You gave me a boundary of ten." not in answer:
                raise ValueError("candidate did not retain predecessor request context")
        before = saved()
        run(executable, "update", "rollback", "--yes", "--root", str(root))
        preserved(before)
        resume()

        for after in (False, True):
            before = saved()
            interrupt_install(root, bin_dir, candidate, raw, after=after)
            expected = candidate.version if after else previous.version
            version(expected)
            result = json.loads(
                run(
                    executable,
                    "update",
                    "recover",
                    "--yes",
                    "--root",
                    str(root),
                    "--json",
                )
            )
            if (
                result.get("installed") != expected
                or (root / "transaction.json").exists()
            ):
                raise ValueError(
                    "frozen recovery did not preserve the activation commit"
                )
            preserved(before)
            resume()
            if after:
                run(executable, "update", "rollback", "--yes", "--root", str(root))
                version(previous.version)

        before = saved()
        try:
            app_install.install(root, bin_dir, candidate, raw + b"tampered")
        except ReleaseError:
            pass
        else:
            raise ValueError("altered candidate archive was accepted")
        version(previous.version)
        preserved(before)
        install_native(args.candidate, candidate, bootstrap)
        before = saved()
        damaged = root / "current" / "qualification-tamper"
        damaged.write_bytes(b"inert runtime tamper")
        try:
            run(executable, "update", "recover", "--yes", "--root", str(root))
        except subprocess.CalledProcessError:
            pass
        else:
            raise ValueError("frozen recovery accepted altered runtime contents")
        damaged.unlink()
        run(executable, "update", "recover", "--yes", "--root", str(root))
        preserved(before)
        resume()
        before = saved()
        run(executable, "update", "uninstall", "--yes", "--root", str(root))
        preserved(before)
        if (
            executable.exists()
            or executable.is_symlink()
            or (root / "releases").exists()
        ):
            raise ValueError("candidate uninstall retained an owned launcher/runtime")
        install_native(args.predecessor, previous, previous_bootstrap)
        preserved(before)
        version(previous.version)
        resume()
        before = saved()
        run(executable, "update", "uninstall", "--yes", "--root", str(root))
        preserved(before)
        if executable.is_symlink() or (root / "releases").exists():
            raise ValueError("predecessor uninstall retained an owned launcher/runtime")

    evidence = {
        "schema": 1,
        "platform": platform_id(),
        "predecessor_version": previous.version,
        "predecessor_source": previous.source_commit,
        "predecessor_archive_sha256": hashlib.sha256(previous_raw).hexdigest(),
        "predecessor_metadata_sha256": hashlib.sha256(previous.raw).hexdigest(),
        "predecessor_bootstrap_sha256": expected_bootstrap,
        "candidate_version": candidate.version,
        "candidate_source": candidate.source_commit,
        "candidate_archive_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate_metadata_sha256": hashlib.sha256(candidate.raw).hexdigest(),
        "candidate_bootstrap_sha256": hashlib.sha256(
            bootstrap.read_bytes()
        ).hexdigest(),
        "publisher": "enrolled_production_root_unpatched",
        "session_backends": ["snapshot", "sqlite"],
        "cold_resume_both_versions": True,
        "candidate_written_session_rollback": True,
        "pre_and_post_activation_recovery": True,
        "archive_runtime_tamper_refused": True,
        "state_preserved": True,
        "uninstall_both_versions": True,
        "external_python_node_required": False,
        "paid_calls": 0,
        "candidate_publication": "not_authorized",
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(str(error.stderr)[-1000:], file=sys.stderr)
        raise
