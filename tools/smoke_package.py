"""Install the wheel and exercise both deterministic replay paths."""

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> int:
    wheel = Path("dist/mos_eisley-0.1.0-py3-none-any.whl").resolve()
    with TemporaryDirectory(prefix="mos-eisley-wheel-") as directory:
        root = Path(directory)
        python = root / "venv/bin/python"
        subprocess.run(
            ["uv", "venv", str(root / "venv"), "--python", "3.12"], check=True
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--require-hashes",
                "-r",
                "requirements.runtime.txt",
            ],
            check=True,
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
            check=True,
        )
        command = str(root / "venv/bin/mos-eisley")
        demo = subprocess.run(
            [command, "demo", "--output", str(root / "runs"), "--json"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if demo.returncode != 1:
            raise ValueError("wheel demo did not return expected revise status")
        event = json.loads(demo.stdout.splitlines()[0])
        subprocess.run([command, "replay", event["path"]], cwd=root, check=True)
        agent = subprocess.run(
            [
                command,
                "agent-demo",
                "--output",
                str(root / "agent-runs"),
                "--json",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        agent_event = json.loads(agent.stdout)
        subprocess.run(
            [command, "agent-replay", agent_event["path"]], cwd=root, check=True
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
