"""Install the wheel and exercise replay plus an actual MCP subprocess call."""

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
        server = root / "mcp_fixture.py"
        server.write_text(Path("tests/fixtures/mcp_server.py").read_text())
        config = root / "mcp.json"
        config.write_text(
            json.dumps(
                {
                    "command": str(python),
                    "args": [str(server)],
                    "cwd": str(root),
                    "tools": {"echo": "read"},
                }
            )
        )
        call = root / "call.json"
        call.write_text(
            json.dumps(
                {
                    "id": "wheel-call",
                    "name": "echo",
                    "args": {"value": "wheel-fixture"},
                }
            )
        )
        mcp = subprocess.run(
            [command, "mcp-call", "--config", str(config), "--call", str(call)],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(mcp.stdout)
        if result["is_error"] or json.loads(result["content"])[
            "structured_content"
        ] != {"value": "wheel-fixture"}:
            raise ValueError("installed MCP client returned the wrong fixture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
