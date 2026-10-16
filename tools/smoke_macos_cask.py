"""Native read-only DMG layout/runtime evidence, separate from brew qualification."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from tools.package_macos_cask import load_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--team-id", help="Expected publisher Apple Team ID")
    args = parser.parse_args()
    package = load_package(
        args.receipt, development=args.development, expected_team=args.team_id
    )
    with tempfile.TemporaryDirectory(prefix="mos-cask-smoke-") as temporary:
        base = Path(temporary).resolve()
        mount = base / "mount"
        mount.mkdir()
        subprocess.run(
            [
                "hdiutil",
                "attach",
                "-readonly",
                "-nobrowse",
                "-mountpoint",
                str(mount),
                str(package.image),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        try:
            executable = mount / "Mos Eisley/mos"
            environment = {
                key: value
                for key, value in os.environ.items()
                if key in {"LANG", "LC_ALL", "TMPDIR"}
            }
            environment.update(HOME=str(base), PATH="/nonexistent")

            def run(*arguments: str, input_text: str = "") -> str:
                return subprocess.run(
                    [str(executable), *arguments],
                    env=environment,
                    input=input_text,
                    text=True,
                    capture_output=True,
                    timeout=90,
                    check=True,
                ).stdout

            if run("--version").strip() != f"mos-eisley {package.version}":
                raise ValueError("mounted cask runtime version mismatch")
            run("--help")
            setup = json.loads(run("setup", "--json"))
            if setup["credentials_required_to_install"] or any(
                setup["providers"].values()
            ):
                raise ValueError("mounted setup did not remain credential-free")
            root = base / "update-state"
            run("update", "disable", "--root", str(root))
            status = json.loads(run("update", "check", "--root", str(root), "--json"))
            if status["origin"] != "homebrew-cask" or status["status"] != "disabled":
                raise ValueError("mounted runtime did not retain cask ownership")
            cassette = base / "recorded.json"
            run("conversation-demo", "--output", str(cassette))
            workspace = base / "workspace"
            workspace.mkdir()
            common = [
                "--plain",
                "--no-memory",
                "--storage",
                str(base / "sessions"),
                "-C",
                str(workspace),
            ]
            response = run(
                "chat",
                *common,
                "--cassette",
                str(cassette),
                input_text="Remember that the fixture boundary is ten.\n",
            )
            resumed = run("resume", "--last", *common)
            if any(
                "The fixture boundary is ten." not in output
                for output in (response, resumed)
            ):
                raise ValueError(
                    "mounted native chat/cold resume lost recorded context"
                )
        finally:
            subprocess.run(
                ["hdiutil", "detach", str(mount)],
                check=True,
                capture_output=True,
                timeout=120,
            )
    evidence = {
        "schema": 1,
        "platform": package.platform,
        "version": package.version,
        "source_commit": package.source,
        "sha256": package.sha256,
        "development": args.development,
        "read_only_mount": True,
        "credential_free_setup": True,
        "chat_cold_resume": True,
        "external_python_node_required": False,
        "cask_origin": True,
        "brew_lifecycle_qualified": False,
        "publication_authorized": False,
        "paid_calls": 0,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
