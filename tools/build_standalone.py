"""Build an OS-native, self-contained onedir bundle and immutable archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import tomllib
from pathlib import Path


def main() -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--output", type=Path, default=Path("dist/standalone"))
    args = command.parse_args()
    from mos_eisley.app_release import platform_id

    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "--python",
            "3.12.14",
            "--managed-python",
            "--group",
            "distribution",
            "python",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "mos",
            "--noupx",
            "--distpath",
            str(output / "bundle"),
            "--workpath",
            str(output / "build"),
            "--specpath",
            str(output / "build"),
            "--collect-all",
            "mos_eisley",
            "--collect-all",
            "keyring",
            "--collect-all",
            "cryptography",
            "--copy-metadata",
            "mos-eisley",
            "--recursive-copy-metadata",
            "mcp",
            "tools/app_entry.py",
        ],
        check=True,
    )
    bundle = output / "bundle/mos"
    subprocess.run([str(bundle / "mos"), "--version"], check=True)
    subprocess.run([str(bundle / "mos"), "setup", "--json"], check=True)
    archive = output / f"mos-{version}-{platform_id()}.tar.gz"
    # Dereference PyInstaller's local library symlinks at publication so the
    # installer can reject every link in an archive without platform exceptions.
    with tarfile.open(archive, "w:gz", dereference=True) as stream:
        for path in sorted(bundle.iterdir()):
            stream.add(path, arcname=path.name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.with_suffix(".json")).write_text(
        json.dumps(
            {
                "platform": platform_id(),
                "size": archive.stat().st_size,
                "sha256": digest,
                "file": archive.name,
            },
            sort_keys=True,
        )
    )
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
