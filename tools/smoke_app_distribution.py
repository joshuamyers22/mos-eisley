"""Real frozen-runtime install and recovery; ephemeral publisher key, no paid calls."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley import app_install, app_release
from mos_eisley.app_install import install, recover, rollback, uninstall
from mos_eisley.app_release import ReleaseError, canonical, parse_release, platform_id


def snapshot(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def qualify_exec_recovery(
    executable: str, environment: dict[str, str], directory: Path
) -> None:
    """Exercise the frozen exec entry point and cold recovery without inference."""
    directory.mkdir()
    for backend in ("snapshot", "sqlite"):
        storage = directory / backend
        arguments = [
            "--no-memory",
            "--storage-backend",
            backend,
            "--storage",
            str(storage),
            "-C",
            str(directory),
        ]
        completed = subprocess.run(
            [
                executable,
                "exec",
                "--json",
                *arguments,
                "Remember that the fixture boundary is ten.",
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=90,
        )
        events = [json.loads(line) for line in completed.stdout.splitlines()]
        results = [event for event in events if event.get("type") == "exec.result"]
        if len(results) != 1 or events[-1] != results[0]:
            raise ValueError("frozen exec did not emit exactly one final result")
        result = results[0]
        if (
            result.get("status") != "completed"
            or result.get("answer") != "The fixture boundary is ten."
            or result.get("persistence_status") != "committed"
            or result.get("effect_status") != "completed"
            or not result.get("operation_id")
            or not isinstance(result.get("recovery_cursor"), int)
            or result["recovery_cursor"] < 2
        ):
            raise ValueError("frozen exec lacks committed operation/recovery evidence")
        resumed = subprocess.run(
            [executable, "resume", "--last", "--plain", *arguments],
            input="What boundary did I give you?\n",
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=90,
        )
        if "You gave me a boundary of ten." not in resumed.stdout:
            raise ValueError("frozen exec cold resume lost its saved context")


def require_rejection(operation: Callable[[], object], message: str) -> None:
    try:
        operation()
    except ReleaseError:
        return
    raise ValueError(message)


def signed_fixture(version: str, raw: bytes, key: Ed25519PrivateKey) -> bytes:
    payload = {
        "schema": 1,
        "version": version,
        "channel": "preview" if "-" in version else "stable",
        "source_commit": "a" * 40,
        "notes": "Ephemeral synthetic publisher for local packaging evidence only.",
        "storage_epoch": app_release.STORAGE_EPOCH,
        "withdrawn": False,
        "artifacts": [
            {
                "platform": platform_id(),
                "url": f"{app_release.RELEASE_ORIGIN}v{version}/"
                f"mos-{version}-{platform_id()}.tar.gz",
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        ],
    }
    return canonical(
        {
            "payload": payload,
            "signature": base64.b64encode(key.sign(canonical(payload))).decode(),
        }
    )


def older_fixture(raw: bytes, version: str) -> bytes:
    """Same frozen code with explicitly synthetic older distribution metadata."""
    output = io.BytesIO()
    replaced = False
    with (
        tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as source,
        tarfile.open(fileobj=output, mode="w:gz") as target,
    ):
        for member in source:
            content = source.extractfile(member) if member.isfile() else None
            if content is not None and member.name.endswith("/METADATA"):
                data = content.read()
                if b"Name: mos-eisley\n" in data:
                    # Wheel metadata normalizes SemVer rc tags to PEP 440.
                    accepted = {version, version.replace("-rc.", "rc")}
                    version_lines = [
                        line
                        for line in data.splitlines(keepends=True)
                        if line.startswith(b"Version:")
                    ]
                    if len(version_lines) != 1 or version_lines[0] not in {
                        f"Version: {value}\n".encode() for value in accepted
                    }:
                        raise ValueError(
                            "frozen distribution version differs from candidate"
                        )
                    data = data.replace(version_lines[0], b"Version: 0.0.0\n")
                    replaced = True
                content.close()
                content = io.BytesIO(data)
                member.size = len(data)
            target.addfile(member, content)
            if content is not None:
                content.close()
    if not replaced:
        raise ValueError("frozen distribution metadata is missing")
    return output.getvalue()


def main() -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--evidence", type=Path)
    command.add_argument(
        "--published-metadata",
        type=Path,
        help="also qualify the production-key bootstrap with signed candidate metadata",
    )
    args = command.parse_args()
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    archive = Path(f"dist/standalone/mos-{version}-{platform_id()}.tar.gz")
    raw = archive.read_bytes()
    previous_raw = older_fixture(raw, version)
    key = Ed25519PrivateKey.generate()
    signed = signed_fixture(version, raw, key)
    previous_signed = signed_fixture("0.0.0", previous_raw, key)
    with tempfile.TemporaryDirectory(prefix="mos-frozen-install-") as temporary:
        base = Path(temporary).resolve()
        root, bin_dir = base / "app with spaces", base / "bin with spaces"
        environment = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(("OPENAI_", "ANTHROPIC_", "PYTHON", "MOS_"))
        }
        environment["HOME"] = str(base)
        # An empty PATH proves the installed application needs neither Python nor
        # Node. Its existing runtime/tool admission must still reject missing Git.
        environment["PATH"] = "/nonexistent"
        bootstrap = Path(f"dist/standalone/mos-install-{platform_id()}").resolve()
        channel = "preview" if "-" in version else "stable"
        metadata = base / "untrusted-release.json"
        metadata.write_bytes(signed)
        supplied_archive = base / archive.name
        supplied_archive.write_bytes(raw)
        rejected = subprocess.run(
            [
                str(bootstrap),
                "--metadata",
                str(metadata),
                "--archive",
                str(supplied_archive),
                "--root",
                str(root),
                "--bin-dir",
                str(bin_dir),
                "--channel",
                channel,
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if rejected.returncode == 0 or "signature" not in rejected.stderr:
            raise ValueError("production bootstrap accepted an untrusted publisher")
        if root.exists() or bin_dir.exists():
            raise ValueError("rejected bootstrap created an installation")
        trusted_bootstrap = "requires_actual_publisher_signed_candidate"
        if args.published_metadata:
            trusted_root, trusted_bin = base / "trusted app", base / "trusted bin"
            subprocess.run(
                [
                    str(bootstrap),
                    "--metadata",
                    str(args.published_metadata.resolve()),
                    "--archive",
                    str(supplied_archive),
                    "--root",
                    str(trusted_root),
                    "--bin-dir",
                    str(trusted_bin),
                    "--channel",
                    channel,
                    "--version",
                    version,
                ],
                env=environment,
                check=True,
                timeout=60,
            )
            from mos_eisley.app_update import policy

            if policy(trusted_root).channel != channel:
                raise ValueError(
                    "bootstrap did not preserve the selected update channel"
                )
            trusted_executable = str(trusted_bin / "mos")
            subprocess.run(
                [
                    trusted_executable,
                    "update",
                    "disable",
                    "--root",
                    str(trusted_root),
                    "--json",
                ],
                env=environment,
                check=True,
                timeout=60,
            )
            qualify_exec_recovery(
                trusted_executable, environment, base / "signed exec recovery"
            )
            subprocess.run(
                [trusted_executable, "setup", "--json"],
                env=environment,
                check=True,
                timeout=60,
            )
            trusted_state, trusted_workspace = (
                base / "trusted state",
                base / "trusted workspace",
            )
            trusted_workspace.mkdir()
            launch = [
                "--plain",
                "--no-memory",
                "--storage",
                str(trusted_state),
                "-C",
                str(trusted_workspace),
            ]
            for action, prompt, answer in (
                (
                    "chat",
                    "Remember that the fixture boundary is ten.",
                    "The fixture boundary is ten.",
                ),
                (
                    "resume",
                    "What boundary did I give you?",
                    "You gave me a boundary of ten.",
                ),
            ):
                conversation = subprocess.run(
                    [
                        trusted_executable,
                        action,
                        *(["--last"] if action == "resume" else []),
                        *launch,
                    ],
                    input=prompt + "\n",
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                )
                if answer not in conversation.stdout:
                    raise ValueError(
                        "publisher-signed installed conversation lost context"
                    )
            trusted_retained = snapshot(trusted_state)
            subprocess.run(
                [
                    trusted_executable,
                    "update",
                    "recover",
                    "--yes",
                    "--root",
                    str(trusted_root),
                    "--json",
                ],
                env=environment,
                check=True,
                timeout=60,
            )
            subprocess.run(
                [
                    trusted_executable,
                    "update",
                    "uninstall",
                    "--yes",
                    "--root",
                    str(trusted_root),
                    "--json",
                ],
                env=environment,
                check=True,
                timeout=60,
            )
            if (trusted_bin / "mos").is_symlink() or (
                trusted_root / "releases"
            ).exists():
                raise ValueError(
                    "trusted bootstrap uninstall left the runtime installed"
                )
            if not trusted_retained or trusted_retained != snapshot(trusted_state):
                raise ValueError(
                    "publisher-signed recovery/uninstall changed saved state"
                )
            trusted_bootstrap = "passed_actual_publisher_signed_candidate"
        with patch.object(
            app_release,
            "PUBLISHER_PUBLIC_KEY",
            key.public_key().public_bytes_raw().hex(),
        ):
            release = parse_release(signed)
            previous = parse_release(previous_signed)
            install(root, bin_dir, previous, previous_raw)
            from mos_eisley.app_update import change_policy

            change_policy(root, "disabled")
            executable = str(bin_dir / "mos")
            qualify_exec_recovery(executable, environment, base / "exec recovery")
            subprocess.run([executable, "--version"], env=environment, check=True)
            subprocess.run(
                [executable, "--help"],
                env=environment,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            setup = json.loads(
                subprocess.check_output(
                    [executable, "setup", "--json"],
                    env=environment,
                    text=True,
                )
            )
            if setup["credentials_required_to_install"] or any(
                setup["providers"].values()
            ):
                raise ValueError("setup did not remain credential-free")
            cassette = base / "recorded.json"
            subprocess.run(
                [executable, "conversation-demo", "--output", str(cassette)],
                env=environment,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            state = base / "state"
            workspace = base / "workspace"
            workspace.mkdir()
            conversation = subprocess.run(
                [
                    executable,
                    "chat",
                    "--plain",
                    "--no-memory",
                    "--cassette",
                    str(cassette),
                    "--storage",
                    str(state),
                    "-C",
                    str(workspace),
                ],
                input="Remember that the fixture boundary is ten.\n",
                text=True,
                env=environment,
                capture_output=True,
                timeout=60,
                check=False,
            )
            if conversation.returncode != 0:
                raise ValueError(f"frozen chat failed: {conversation.stderr[-1000:]}")
            if "The fixture boundary is ten." not in conversation.stdout:
                raise ValueError("installed chat did not execute its recorded turn")
            before = {
                str(path.relative_to(state)): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in state.rglob("*")
                if path.is_file()
            }
            require_rejection(
                lambda: install(root, bin_dir, release, raw + b"tampered"),
                "installer accepted an altered archive",
            )
            if snapshot(state) != before:
                raise ValueError("rejected archive changed session state")
            original_activate = app_install.activate_pointer

            def interrupt_after_activation(path: Path, name: str, value: str) -> None:
                original_activate(path, name, value)
                if name == "current":
                    raise OSError("synthetic interruption after activation commit")

            with patch.object(
                app_install, "activate_pointer", interrupt_after_activation
            ):
                try:
                    install(root, bin_dir, release, raw)
                except OSError as error:
                    if str(error) != "synthetic interruption after activation commit":
                        raise
                else:
                    raise ValueError("interrupted installation unexpectedly completed")
            if not (root / "transaction.json").exists():
                raise ValueError("interruption did not retain the pending transaction")
            recover(root)
            if (root / "transaction.json").exists() or snapshot(state) != before:
                raise ValueError(
                    "recovery did not clear the transaction and preserve state"
                )
            actual = subprocess.check_output(
                [executable, "--version"], env=environment, text=True
            ).strip()
            if actual != f"mos-eisley {version}":
                raise ValueError("upgrade did not activate the target version")
            rollback(root)
            actual = subprocess.check_output(
                [executable, "--version"], env=environment, text=True
            ).strip()
            if actual != "mos-eisley 0.0.0":
                raise ValueError("rollback did not activate the synthetic predecessor")
            install(root, bin_dir, release, raw)
            damaged = root / "current" / "qualification-tamper"
            damaged.write_bytes(b"synthetic runtime tamper")
            require_rejection(
                lambda: recover(root), "recovery accepted a damaged runtime"
            )
            damaged.unlink()
            recover(root)
            after = {
                str(path.relative_to(state)): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in state.rglob("*")
                if path.is_file()
            }
            if not before or before != after:
                raise ValueError("reinstall/recovery changed session state")
            resumed = subprocess.run(
                [
                    executable,
                    "resume",
                    "--last",
                    "--plain",
                    "--no-memory",
                    "--storage",
                    str(state),
                    "-C",
                    str(workspace),
                ],
                input="What boundary did I give you?\n",
                text=True,
                env=environment,
                capture_output=True,
                timeout=60,
                check=False,
            )
            if resumed.returncode != 0:
                raise ValueError(f"frozen resume failed: {resumed.stderr[-1000:]}")
            if "You gave me a boundary of ten." not in resumed.stdout:
                raise ValueError(
                    "installed resume did not retain recorded conversation context"
                )
            retained = snapshot(state)
            uninstall(root)
            if (
                retained != snapshot(state)
                or (bin_dir / "mos").is_symlink()
                or (root / "releases").exists()
            ):
                raise ValueError(
                    "uninstall did not remove the runtime and preserve state"
                )
    evidence = {
        "schema": 1,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "platform": platform_id(),
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "self_contained": True,
        "credential_free_setup": True,
        "bootstrap_untrusted_signature_rejected": True,
        "bootstrap_trusted_install": trusted_bootstrap,
        "bootstrap_sha256": hashlib.sha256(bootstrap.read_bytes()).hexdigest(),
        "interrupted_activation_recovery": True,
        "archive_runtime_tamper_rejected": True,
        "chat_resume": True,
        "exec_recovery_snapshot_sqlite": True,
        "state_preserved": True,
        "upgrade_rollback": "passed_synthetic_older_metadata_same_code",
        "publisher": "ephemeral_test_only",
        "paid_calls": 0,
    }
    serialized = json.dumps(evidence, sort_keys=True)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(serialized + "\n")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
