"""Build a platform-native installer that needs no external Python."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from mos_eisley.app_release import platform_id


def main() -> int:
    output = Path("dist/standalone").absolute()
    output.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    inventory_command = [
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
        "tools.release_sbom",
    ]
    data = output / "bootstrap-inventory-inputs"
    subprocess.run(
        inventory_command
        + [
            "record-runtime",
            "--destination",
            str(data),
            "--kind",
            "bootstrap",
            "--version",
            version,
            "--commit",
            commit,
        ],
        check=True,
    )
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
            "--onefile",
            "--noupx",
            "--name",
            f"mos-install-{platform_id()}",
            "--distpath",
            str(output),
            "--workpath",
            str(output / "bootstrap-build"),
            "--specpath",
            str(output / "bootstrap-build"),
            "--collect-all",
            "cryptography",
            "--recursive-copy-metadata",
            "cryptography",
            "--copy-metadata",
            "mos-eisley",
            "--add-data",
            str(data / "mos-runtime.json") + ":.",
            "--add-data",
            str(data / "python-runtime-LICENSE.txt") + ":.",
            "tools/app_bootstrap.py",
        ],
        check=True,
    )
    subprocess.run([str(output / f"mos-install-{platform_id()}"), "--help"], check=True)
    subprocess.run(
        inventory_command
        + [
            "verify-runtime",
            "--destination",
            str(data),
            "--kind",
            "bootstrap",
            "--executable",
            str(output / f"mos-install-{platform_id()}"),
        ],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
