"""Exercise review and replay in one ephemeral, unprivileged container."""

import subprocess

SMOKE = """
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from mos_eisley.cli import main
if os.getuid() != 10001:
    raise RuntimeError('unexpected container UID')
with TemporaryDirectory() as root:
    if main(['demo', '--output', root]) != 1:
        raise RuntimeError('expected revise exit status')
    run = next(path for path in Path(root).iterdir() if path.is_dir())
    if main(['replay', str(run)]) != 0:
        raise RuntimeError('replay failed')
"""


def main() -> int:
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--entrypoint",
            "python",
            "mos-eisley:local",
            "-c",
            SMOKE,
        ],
        check=True,
        timeout=30,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
