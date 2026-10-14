"""Install the frozen archive through real Homebrew in an isolated local prefix."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import tomllib
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley import app_release
from mos_eisley.app_release import canonical, parse_release, platform_id


def main() -> int:
    command_line = argparse.ArgumentParser(description=__doc__)
    command_line.add_argument("--published-metadata", type=Path)
    command_line.add_argument("--evidence", type=Path)
    args = command_line.parse_args()
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    brew = shutil.which("brew")
    if brew is None:
        raise ValueError("actual Homebrew is required for this platform qualification")
    repository = Path(
        subprocess.check_output([brew, "--repository"], text=True).strip()
    )
    portable = sorted(
        (repository / "Library/Homebrew/vendor/portable-ruby").glob("*/bin/ruby")
    )
    archive = Path(f"dist/standalone/mos-{version}-{platform_id()}.tar.gz").resolve()
    work = Path(".work").resolve()
    work.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mos-brew-install-", dir=work) as temporary:
        base = Path(temporary).resolve()
        if args.published_metadata:
            assets = args.published_metadata.resolve().parent
            if args.published_metadata.name != "release.json":
                raise ValueError("signed metadata must be named release.json")
            trust = nullcontext()
            publisher = "actual_enrolled_candidate"
        else:
            assets = base / "assets"
            assets.mkdir()
            shutil.copyfile(archive, assets / archive.name)
            key = Ed25519PrivateKey.generate()
            payload = {
                "schema": 1,
                "version": version,
                "channel": "preview" if "-rc." in version else "stable",
                "source_commit": "a" * 40,
                "notes": "Synthetic local generated-formula qualification only.",
                "storage_epoch": 1,
                "withdrawn": False,
                "artifacts": [
                    {
                        "platform": platform_id(),
                        "url": f"{app_release.RELEASE_ORIGIN}v{version}/{archive.name}",
                        "size": archive.stat().st_size,
                        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    }
                ],
            }
            (assets / "release.json").write_bytes(
                canonical(
                    {
                        "payload": payload,
                        "signature": base64.b64encode(
                            key.sign(canonical(payload))
                        ).decode(),
                    }
                )
            )
            trust = patch.object(
                app_release,
                "PUBLISHER_PUBLIC_KEY",
                key.public_key().public_bytes_raw().hex(),
            )
            publisher = "ephemeral_test_only"
        managers = base / "managers"
        with (
            trust,
            patch.object(
                sys,
                "argv",
                [
                    "package_app_managers.py",
                    "--artifacts",
                    str(assets),
                    "--output",
                    str(managers),
                ],
            ),
        ):
            release = parse_release((assets / "release.json").read_bytes())
            if release.version != version:
                raise ValueError(
                    "formula release differs from the exact candidate version"
                )
            artifact = release.artifact(platform_id())
            try:
                runpy.run_path("tools/package_app_managers.py", run_name="__main__")
            except SystemExit as result:
                if result.code != 0:
                    raise
        formula_name = (
            "mos-eisley-preview" if release.channel == "preview" else "mos-eisley"
        )
        generated = (managers / f"{formula_name}.rb").read_text()
        remote_url = f'url "{artifact.url}"'
        if generated.count(remote_url) != 1:
            raise ValueError(
                "generated formula does not select the exact signed artifact"
            )
        local_formula = generated.replace(remote_url, f'url "{archive.as_uri()}"')
        prefix = base / "prefix"
        clone = prefix / "Homebrew"
        subprocess.run(
            ["git", "clone", "--shared", str(repository), str(clone)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        environment = {
            **{
                name: value
                for name, value in os.environ.items()
                if not name.startswith(("OPENAI_", "ANTHROPIC_", "PYTHON", "MOS_"))
            },
            "HOMEBREW_NO_AUTO_UPDATE": "1",
            "HOMEBREW_NO_ANALYTICS": "1",
            "HOMEBREW_NO_INSTALL_CLEANUP": "1",
            "HOMEBREW_NO_AUTOREMOVE": "1",
            "HOMEBREW_DEVELOPER": "1",
            "HOMEBREW_CACHE": str(base / "cache"),
            "HOMEBREW_LOGS": str(base / "logs"),
        }
        if portable:
            environment["HOMEBREW_RUBY_PATH"] = str(portable[-1])
        tap = clone / "Library/Taps/qualification/homebrew-mos-eisley"
        formula = tap / f"Formula/{formula_name}.rb"
        formula.parent.mkdir(parents=True)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != artifact.sha256:
            raise ValueError("local archive differs from the signed formula")
        formula.write_text(local_formula)
        subprocess.run(["git", "init", str(tap)], check=True, stdout=subprocess.DEVNULL)
        command = str(clone / "bin/brew")
        installed_prefix = Path(
            subprocess.check_output(
                [command, "--prefix"], env=environment, text=True
            ).strip()
        )
        selected = f"qualification/mos-eisley/{formula_name}"
        subprocess.run([command, "install", selected], env=environment, check=True)
        subprocess.run(
            [str(installed_prefix / "bin/mos"), "--version"],
            env=environment,
            check=True,
        )
        subprocess.run(
            [str(installed_prefix / "bin/mos"), "setup", "--json"],
            env=environment,
            check=True,
        )
        subprocess.run([command, "test", selected], env=environment, check=True)
        subprocess.run([command, "uninstall", selected], env=environment, check=True)
        if (installed_prefix / "bin/mos").exists() or (
            installed_prefix / "bin/mos"
        ).is_symlink():
            raise ValueError("Homebrew left an active launcher after uninstall")
    evidence = {
        "platform": platform_id(),
        "archive_sha256": digest,
        "generated_formula_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "formula": formula_name,
        "formula_mutation": "selected_archive_url_only",
        "publisher": publisher,
        "homebrew_install_launch_test_uninstall": "passed_generated_formula",
        "public_tap": "not_published",
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
