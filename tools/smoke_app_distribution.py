"""Real frozen-runtime install and recovery; ephemeral publisher key, no paid calls."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley import app_release
from mos_eisley.app_install import install, recover, rollback, uninstall
from mos_eisley.app_release import canonical, parse_release, platform_id


def signed_fixture(version: str, raw: bytes, key: Ed25519PrivateKey) -> bytes:
    payload = {
        "schema": 1,
        "version": version,
        "channel": "stable",
        "source_commit": "a" * 40,
        "notes": "Ephemeral synthetic publisher for local packaging evidence only.",
        "storage_epoch": 1,
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
                    data = data.replace(
                        f"Version: {version}\n".encode(), b"Version: 0.0.0\n"
                    )
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
            subprocess.run([executable, "--version"], env=environment, check=True)
            subprocess.run(
                [executable, "--help"],
                env=environment,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run([executable, "setup", "--json"], env=environment, check=True)
            state = base / "state"
            workspace = base / "workspace"
            workspace.mkdir()
            conversation = subprocess.run(
                [
                    executable,
                    "chat",
                    "--plain",
                    "--no-memory",
                    "--storage",
                    str(state),
                    "-C",
                    str(workspace),
                ],
                input="/quit\n",
                text=True,
                env=environment,
                capture_output=True,
                timeout=60,
                check=False,
            )
            if conversation.returncode != 0:
                raise ValueError(f"frozen chat failed: {conversation.stderr[-1000:]}")
            before = {
                str(path.relative_to(state)): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in state.rglob("*")
                if path.is_file()
            }
            install(root, bin_dir, release, raw)
            recover(root)
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
                input="/quit\n",
                text=True,
                env=environment,
                capture_output=True,
                timeout=60,
                check=False,
            )
            if resumed.returncode != 0:
                raise ValueError(f"frozen resume failed: {resumed.stderr[-1000:]}")
            uninstall(root)
            if not state.exists():
                raise ValueError("uninstall removed session state")
    print(
        json.dumps(
            {
                "platform": platform_id(),
                "archive_sha256": hashlib.sha256(raw).hexdigest(),
                "self_contained": True,
                "credential_free_setup": True,
                "chat_resume": True,
                "state_preserved": True,
                "upgrade_rollback": "passed_synthetic_older_metadata_same_code",
                "publisher": "ephemeral_test_only",
                "paid_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
