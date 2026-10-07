"""Owner-selected browser login through official clients; never copy their tokens."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


def add_command(add_parser: Callable[..., argparse.ArgumentParser]) -> None:
    command = add_parser(
        "auth",
        help="Browser sign-in through an official provider client",
    )
    command.add_argument("action", choices=("login", "status", "logout"))
    command.add_argument("provider", choices=("openai", "anthropic"))


def auth_command(provider: str, action: str) -> tuple[str, ...]:
    if provider == "openai":
        return {
            "login": ("codex", "login"),
            "status": ("codex", "login", "status"),
            "logout": ("codex", "logout"),
        }[action]
    if provider == "anthropic":
        return ("claude", "auth", action)
    raise ValueError("unsupported account provider")


def run_command(args: argparse.Namespace) -> int:
    if not sys.stdin.isatty() and args.action == "login":
        print("Browser login requires an interactive owner terminal.", file=sys.stderr)
        return 2
    selected = auth_command(args.provider, args.action)
    # Ignore relative PATH entries and executables inside the active project.
    # This selects an owner-installed client; it does not attest its publisher.
    current = Path.cwd().resolve()
    directories: list[str] = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        directory = Path(entry)
        if not entry or not directory.is_absolute():
            continue
        if current != Path.home().resolve() and directory.resolve().is_relative_to(
            current
        ):
            continue
        directories.append(entry)
    executable = shutil.which(selected[0], path=os.pathsep.join(directories))
    if executable is None:
        print(
            f"Install the official {selected[0]} client first. "
            "See mos setup and the provider installation documentation.",
            file=sys.stderr,
        )
        return 2
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CODE_OAUTH_TOKEN",
            "CODEX_API_KEY",
            "CODEX_ACCESS_TOKEN",
            "OPENAI_ACCESS_TOKEN",
        }
    }
    # Login runs from the owner's home. Mos supplies no project instructions,
    # provider API keys or model prompt; native-client configuration still applies.
    try:
        result = subprocess.run(
            [executable, *selected[1:]],
            cwd=Path.home(),
            env=environment,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("Provider login did not complete; retry explicitly.", file=sys.stderr)
        return 2
    if args.action == "login" and result.returncode == 0:
        print(
            "Provider account sign-in completed in the official client. "
            "Subscription-backed Mos inference is a separate route and remains "
            "unavailable until its adapter and qualification pass. "
            "API-key routes are not silently selected."
        )
    return result.returncode
