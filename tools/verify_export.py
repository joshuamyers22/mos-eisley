"""Compare the runtime export to the lock without rewriting tracked files."""

import subprocess
from pathlib import Path


def main() -> int:
    result = subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-header"],
        check=True,
        capture_output=True,
        text=True,
    )
    actual = Path("requirements.runtime.txt").read_text()
    lines = "\n".join(line for line in actual.splitlines() if not line.startswith("#"))
    expected = "\n".join(
        line for line in result.stdout.splitlines() if not line.startswith("#")
    )
    if lines != expected:
        raise ValueError("runtime export is stale; run make export-runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
