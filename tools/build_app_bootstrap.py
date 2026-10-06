"""Build a platform-native installer that needs no external Python."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mos_eisley.app_release import platform_id


def main() -> int:
    output = Path("dist/standalone").absolute()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
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
            "tools/app_bootstrap.py",
        ],
        check=True,
    )
    subprocess.run([str(output / f"mos-install-{platform_id()}"), "--help"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
