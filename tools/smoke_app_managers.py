"""Exercise generated local npm packages and Homebrew formula without publishing."""

from __future__ import annotations

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
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley import app_release
from mos_eisley.app_release import canonical, platform_id


def main() -> int:
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    artifact = Path(f"dist/standalone/mos-{version}-{platform_id()}.tar.gz").resolve()
    key = Ed25519PrivateKey.generate()
    with tempfile.TemporaryDirectory(prefix="mos-manager-smoke-") as temporary:
        base = Path(temporary).resolve()
        assets = base / "assets"
        assets.mkdir()
        shutil.copyfile(artifact, assets / artifact.name)
        payload = {
            "schema": 1,
            "version": version,
            "channel": "stable",
            "source_commit": "a" * 40,
            "notes": "Synthetic local package-manager fixture; "
            "not publication evidence.",
            "storage_epoch": 1,
            "withdrawn": False,
            "artifacts": [
                {
                    "platform": platform_id(),
                    "url": f"{app_release.RELEASE_ORIGIN}v{version}/{artifact.name}",
                    "size": artifact.stat().st_size,
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                }
            ],
        }
        signed = canonical(
            {
                "payload": payload,
                "signature": base64.b64encode(key.sign(canonical(payload))).decode(),
            }
        )
        (assets / "release.json").write_bytes(signed)
        managers = base / "managers"
        with (
            patch.object(
                app_release,
                "PUBLISHER_PUBLIC_KEY",
                key.public_key().public_bytes_raw().hex(),
            ),
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
            try:
                runpy.run_path("tools/package_app_managers.py", run_name="__main__")
            except SystemExit as result:
                if result.code != 0:
                    raise
        environment = os.environ.copy()
        npm = shutil.which("npm")
        if npm is None:
            node_bin = Path.home() / ".cache/pyright-python/nodeenv/bin"
            environment["PATH"] = f"{node_bin}:{environment.get('PATH', '')}"
            npm = shutil.which("npm", path=environment["PATH"])
        if npm is None:
            raise ValueError("actual npm is required for this qualification")
        tarballs: list[Path] = []
        for directory in (managers / "npm" / platform_id(), managers / "npm/main"):
            result = subprocess.run(
                [npm, "pack", "--json", "--ignore-scripts"],
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            name = json.loads(result.stdout)[0]["filename"]
            tarballs.append(directory / name)
        installed = base / "npm-installed"
        # Explicit local platform tarball replaces registry discovery for this
        # offline qualification. Both tarballs retain their real public names.
        subprocess.run(
            [
                npm,
                "install",
                "--prefix",
                str(installed),
                "--offline",
                "--ignore-scripts",
                "--omit=optional",
                *map(str, tarballs),
            ],
            env=environment,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        command = installed / "node_modules/.bin/mos"
        subprocess.run([str(command), "--version"], env=environment, check=True)
        subprocess.run([str(command), "setup", "--json"], env=environment, check=True)
        brew = shutil.which("brew")
        brew_status = "not_available"
        if brew:
            # Syntax and actual formula loading are checked without installing
            # into an existing user's Cellar or requiring unpublished endpoints.
            subprocess.run(
                [brew, "ruby", "--", "-c", str(managers / "mos-eisley.rb")],
                env={
                    **environment,
                    "HOMEBREW_NO_AUTO_UPDATE": "1",
                    "HOMEBREW_DEVELOPER": "1",
                },
                check=True,
            )
            brew_status = "real_formula_syntax_only"
        print(
            json.dumps(
                {
                    "platform": platform_id(),
                    "npm_pack_install_launch": "passed_offline_local_tarballs",
                    "homebrew": brew_status,
                    "registry_publication": "not_attempted",
                    "paid_calls": 0,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
