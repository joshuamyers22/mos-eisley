"""Bounded native-subscription chat setup using existing immutable grants."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from uuid import uuid4

from mos_eisley.providers.claude_subscription import status as claude_status
from mos_eisley.providers.codex_subscription import select_client, status
from mos_eisley.subscription_authorization import read_authorization
from mos_eisley.subscription_usage import private_directory


def start_chat(args: argparse.Namespace) -> int:
    from mos_eisley.cli import main
    from mos_eisley.conversation_subscription import check_authority
    from mos_eisley.subscription_cli import create_authorization

    claude = args.provider == "anthropic_subscription"
    label = "Claude" if claude else "ChatGPT"
    consent = (
        args.allow_data_transfer,
        args.allow_subscription_usage,
        args.accept_unverified_billing_and_native_retries,
    )
    if not all(consent):
        if not sys.stdin.isatty():
            print(
                "Subscription chat requires explicit transfer, usage "
                "and native-retry consent.",
                file=sys.stderr,
            )
            return 2
        print(f"{label} subscription chat sends your messages to the provider.")
        if args.resume is None:
            print(
                f"Up to {args.max_invocations} invocations over "
                f"{args.valid_for_seconds} seconds."
            )
        else:
            print("The saved session's original limits and expiry apply.")
        print(
            "Native retries can consume quota or credits; "
            "local limits do not cap billing."
        )
        try:
            answer = input("Start this bounded subscription session? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            return 2
        if answer.strip().lower() != "y":
            return 2
    if (
        not 1 <= args.max_invocations <= 64
        or not 1 <= args.valid_for_seconds <= 3600
        or not 1 <= args.timeout <= 120
    ):
        raise ValueError("Subscription session limits are invalid")
    client = select_client(args.client, name="claude" if claude else "codex")
    workspace = args.workspace.resolve(strict=True)
    if not workspace.is_dir() or client.is_relative_to(workspace):
        print(
            "Choose a project directory outside the native client "
            "installation with -C PATH.",
            file=sys.stderr,
        )
        return 2
    state = args.state_dir.absolute()
    if args.resume is not None and re.fullmatch(r"[0-9a-f]{32}", args.resume) is None:
        raise ValueError("Subscription session identity is invalid")
    if args.resume is None:
        state.mkdir(mode=0o700, exist_ok=True)
    parent = private_directory(state)
    try:
        session_id = args.resume or uuid4().hex
        if args.resume is None:
            os.mkdir(session_id, mode=0o700, dir_fd=parent)
    finally:
        os.close(parent)
    scope = state / session_id
    descriptor = private_directory(scope)
    os.close(descriptor)
    authorization = scope / "authorization.json"
    authority = None
    if args.resume is not None:
        authority = read_authorization(authorization)
        authority.check_current(workspace, session_id)
        grant = authority.grant("chat")
        if (
            grant.provider != args.provider
            or grant.client != client
            or (args.model is not None and args.model != grant.model)
            or (args.effort is not None and args.effort != grant.effort)
        ):
            raise ValueError("Resume route differs from the saved scope")
        check_authority(authority, authorization, "chat")
    readiness = asyncio.run(claude_status(client) if claude else status(client))
    if readiness["client_version_supported"] is not True:
        print(
            f"The installed {label} client version is unsupported. "
            "Use mos subscription status --provider PROVIDER to check compatibility.",
            file=sys.stderr,
        )
        return 2
    if readiness["subscription_signed_in"] is not True:
        print(
            f"Sign in first: mos auth login {'anthropic' if claude else 'openai'}",
            file=sys.stderr,
        )
        return 2
    if args.resume is None:
        usage = scope / "usage"
        usage.mkdir(mode=0o700)
        create_authorization(
            argparse.Namespace(
                output=authorization,
                workspace=workspace,
                usage_root=usage,
                session_id=session_id,
                valid_for_seconds=args.valid_for_seconds,
                grant=[
                    (
                        "chat",
                        args.provider,
                        args.model or ("claude-sonnet-5" if claude else "gpt-6-sol"),
                        args.effort or ("high" if claude else "medium"),
                        str(client),
                        str(args.max_invocations),
                    )
                ],
                max_invocations=args.max_invocations,
                max_input_bytes=128000,
                max_output_bytes=8000,
                max_output_tokens=2048,
                timeout=args.timeout,
                allow_data_transfer=True,
                allow_subscription_usage=True,
                accept_unverified_billing_and_native_retries=True,
            ),
            announce=False,
        )
        authority = read_authorization(authorization)
        check_authority(authority, authorization, "chat")
    assert authority is not None
    print(
        f"{label} subscription chat · {authority.grant('chat').model} · "
        f"up to {authority.max_invocations} invocations"
    )
    print(
        f"Session: {session_id} · resume with --resume {session_id} "
        "and the same workspace before expiry."
    )
    arguments = ["resume", session_id] if args.resume is not None else ["chat"]
    return main(
        [
            *arguments,
            "-C",
            str(workspace),
            "--storage",
            str(state / "sessions"),
            "--subscription-authorization",
            str(authorization),
            "--allow-data-transfer",
            "--allow-subscription-usage",
            *(["--plain"] if args.plain else []),
        ]
    )
