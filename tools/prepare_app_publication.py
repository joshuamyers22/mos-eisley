"""Prepare shared release metadata/packages; refuses unenrolled publisher custody."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    encoded = os.environ.pop("MOS_RELEASE_SIGNING_KEY_BASE64", None)
    if encoded is None:
        raise ValueError("owner-provisioned release signing custody is missing")
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) != 32:
        raise ValueError("invalid signing key format")
    with tempfile.TemporaryDirectory(prefix="mos-publisher-") as temporary:
        key_file = Path(temporary) / "key"
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
        subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "python",
                "tools/sign_app_release.py",
                "--key-file",
                str(key_file),
                "--artifacts",
                "dist/standalone",
                "--commit",
                args.commit,
                "--channel",
                "preview" if "-rc." in version else "stable",
                "--notes",
                "See the immutable GitHub release notes for changes "
                "and recovery guidance.",
            ],
            check=True,
        )
    output = Path("dist/standalone")
    shutil.copyfile("distribution/install.sh", output / "install.sh")
    sums = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(output.glob("mos-install-*"))
        if path.is_file()
    ]
    if len(sums) != 4:
        raise ValueError("publication requires four platform bootstraps")
    (output / "BOOTSTRAP_SHA256SUMS").write_text("\n".join(sums) + "\n")
    subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "tools/package_app_managers.py",
            "--artifacts",
            str(output),
        ],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
