"""Application setup, discovery and explicit installation commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast


def add_commands(add_parser: Callable[..., argparse.ArgumentParser]) -> None:
    update = add_parser(
        "update", help="Inspect and explicitly install verified application updates"
    )
    update.add_argument(
        "action",
        nargs="?",
        default="install",
        choices=(
            "install",
            "check",
            "later",
            "skip",
            "disable",
            "enable",
            "managed",
            "stable",
            "preview",
            "recover",
            "rollback",
            "uninstall",
        ),
    )
    update.add_argument("--root", type=Path)
    update.add_argument("--version", dest="target")
    update.add_argument("--yes", action="store_true")
    update.add_argument("--json", action="store_true")
    setup = add_parser(
        "setup", help="Credential-free first-launch readiness and provider guidance"
    )
    setup.add_argument("--json", action="store_true")


def setup_result() -> dict[str, object]:
    import shutil

    from mos_eisley.app_update import installed_version

    return {
        "version": installed_version(),
        "credentials_required_to_install": False,
        "browser_sign_in": {
            "openai": "mos auth login openai (official Codex client)",
            "anthropic": "mos auth login anthropic (official Claude client)",
            "subscription_inference": "adapter and qualification pending",
        },
        "providers": {
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
            "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
        "git_available": shutil.which("git") is not None,
        "docker_available": shutil.which("docker") is not None,
        "next": "Run mos in a project for a recorded conversation. Live "
        "requests require explicit qualified route, transfer and spend selection; "
        "setup makes no paid calls.",
        "credential_guidance": "Use an OS credential loader or a private owner-only "
        "environment file outside the repository. Never paste keys into a chat, "
        "repository or shell history.",
    }


def run_command(args: argparse.Namespace) -> int:
    from mos_eisley.app_install import default_root, recover, rollback, uninstall
    from mos_eisley.app_release import ReleaseError
    from mos_eisley.app_update import change_policy, check, manual_instructions, update
    from mos_eisley.app_update_session import runtime_root

    try:
        if args.command == "setup":
            result = setup_result()
        else:
            root = cast(Path | None, args.root) or runtime_root() or default_root()
            action = cast(str, args.action)
            if action == "check":
                result = check(root, force=True)
            elif action in {
                "later",
                "skip",
                "disable",
                "enable",
                "managed",
                "stable",
                "preview",
            }:
                target = cast(str | None, args.target)
                if action == "skip" and target is None:
                    target = cast(str | None, check(root)["latest"])
                    if target is None:
                        raise ReleaseError("no verified release to skip")
                change_policy(
                    root,
                    {"enable": "automatic", "disable": "disabled"}.get(action, action),
                    target,
                )
                result = {"status": "policy_saved", "action": action}
            elif action in {"recover", "rollback", "uninstall"}:
                if not args.yes:
                    raise ReleaseError(
                        "explicit --yes required for recovery, rollback or uninstall"
                    )
                if action == "uninstall":
                    uninstall(root)
                    result = {"status": "uninstalled", "user_state": "preserved"}
                else:
                    value = recover(root) if action == "recover" else rollback(root)
                    result = {
                        "status": action,
                        "installed": value,
                        "user_state": "preserved",
                    }
            else:
                found = check(root, force=True)
                if found["status"] == "unable_to_check" or not found["available"]:
                    raise ReleaseError(
                        f"no verified available update ({found['status']})"
                    )
                if found["origin"] != "standalone":
                    raise ReleaseError(
                        manual_instructions(
                            cast(str, found["origin"]),
                            cast(str | None, found["latest"]),
                        )
                    )
                selected = cast(str | None, args.target) or cast(str, found["latest"])
                confirmed = bool(args.yes)
                if (
                    not confirmed
                    and not args.json
                    and sys.stdin.isatty()
                    and sys.stdout.isatty()
                ):
                    confirmed = (
                        input(
                            f"Install Mos Eisley {selected} using the standalone "
                            f"installer? [y/N] "
                        )
                        .strip()
                        .lower()
                        == "y"
                    )
                value = update(root, confirmed=confirmed, target=selected)
                result = {
                    "status": "installed",
                    "installed": value,
                    "user_state": "preserved",
                    "next": "Run mos resume --last to explicitly resume; no requests "
                    "are replayed.",
                }
        if args.json:
            print(json.dumps(result, sort_keys=True))
        else:
            for key, value in result.items():
                print(f"{key}: {value}")
        return 0
    except (OSError, ValueError) as error:
        if args.json:
            print(json.dumps({"status": "error", "error": str(error)}))
        else:
            print(f"Mos Eisley: {error}", file=sys.stderr)
        return 2
