"""Owner-selected subscription status and one-use, explicitly consented turns."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path

from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest, TextBlock, Turn
from mos_eisley.providers.codex_subscription import (
    CLIENT_VERSION,
    MAX_INPUT,
    CodexSubscriptionClient,
    select_client,
    status,
)


def add_command(add_parser: Callable[..., argparse.ArgumentParser]) -> None:
    command = add_parser(
        "subscription", help="Explicit local ChatGPT subscription route"
    )
    actions = command.add_subparsers(dest="subscription_action", required=True)
    authorize = actions.add_parser(
        "authorize", help="Create an immutable local subscription usage scope"
    )
    authorize.add_argument("--output", required=True, type=Path)
    authorize.add_argument("--workspace", required=True, type=Path)
    authorize.add_argument("--usage-root", required=True, type=Path)
    authorize.add_argument("--session-id", required=True)
    authorize.add_argument("--valid-for-seconds", type=int, default=600)
    authorize.add_argument(
        "--grant",
        nargs=6,
        action="append",
        required=True,
        metavar=("ROLE", "PROVIDER", "MODEL", "EFFORT", "CLIENT", "CALLS"),
    )
    authorize.add_argument("--max-invocations", type=int, required=True)
    authorize.add_argument("--max-input-bytes", type=int, default=128000)
    authorize.add_argument("--max-output-bytes", type=int, default=8000)
    authorize.add_argument("--max-output-tokens", type=int, default=2048)
    authorize.add_argument("--timeout", type=int, default=30)
    authorize.add_argument("--allow-data-transfer", action="store_true")
    authorize.add_argument("--allow-subscription-usage", action="store_true")
    authorize.add_argument(
        "--accept-unverified-billing-and-native-retries", action="store_true"
    )
    for action in ("status", "ask"):
        selected = actions.add_parser(action)
        selected.add_argument(
            "--provider",
            choices=("openai_subscription", "anthropic_subscription"),
            default="openai_subscription",
        )
        selected.add_argument(
            "--client", type=Path, help="Absolute trusted Codex executable"
        )
        if action == "ask":
            selected.add_argument("--model", required=True)
            selected.add_argument(
                "--effort",
                required=True,
                choices=(
                    "none",
                    "minimal",
                    "low",
                    "medium",
                    "high",
                    "xhigh",
                    "max",
                ),
            )
            selected.add_argument(
                "--attempt",
                required=True,
                type=Path,
                help="New attempt directory under an owner-private parent",
            )
            selected.add_argument("--allow-data-transfer", action="store_true")
            selected.add_argument("--allow-subscription-usage", action="store_true")
            selected.add_argument(
                "--timeout",
                type=float,
                default=60,
                help="Inference deadline; native auth preflight adds up to 30 seconds",
            )
            selected.add_argument("--max-output-bytes", type=int, default=16_000)
            selected.add_argument("--json", action="store_true")
            selected.description = (
                "Read one prompt from stdin. This experimental text route consumes "
                "subscription usage. The deadline and returned-output limit are not "
                "provider billing caps. The native client may retry transport "
                "requests. "
                "Mos cannot replay failed/cancelled attempts. "
                "OpenAI standalone uses gpt-6-sol/medium; Claude uses "
                "its explicit native profiles. "
                "Saved conversational coding and role qualification remain separate."
            )


def run_command(args: argparse.Namespace) -> int:
    try:
        if args.subscription_action == "authorize":
            return create_authorization(args)
        if args.subscription_action == "ask" and (
            not args.allow_data_transfer or not args.allow_subscription_usage
        ):
            raise ValueError("Transfer and subscription-use consent are both required")
        from mos_eisley.core.ports import ModelClient
        from mos_eisley.providers.claude_subscription import (
            CLIENT_VERSION as CLAUDE_VERSION,
        )
        from mos_eisley.providers.claude_subscription import (
            ClaudeSubscriptionClient,
        )
        from mos_eisley.providers.claude_subscription import (
            status as claude_status,
        )

        claude = args.provider == "anthropic_subscription"
        client = select_client(args.client, name="claude" if claude else "codex")
        if args.subscription_action == "status":
            result = asyncio.run(claude_status(client) if claude else status(client))
            print(
                json.dumps(
                    {
                        "provider": args.provider,
                        "required_client_version": CLAUDE_VERSION
                        if claude
                        else CLIENT_VERSION,
                        **result,
                    }
                )
            )
            return 0 if all(result.values()) else 2
        if not 1 <= args.max_output_bytes <= 64_000:
            raise ValueError("Output limit must be 1–64000 UTF-8 bytes")
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError("Prompt exceeds its input limit")
        prompt = raw.decode("utf-8")
        if not prompt.strip():
            raise ValueError("A nonempty prompt is required on stdin")
        request = ModelRequest(
            provider=args.provider,
            model=args.model,
            effort=args.effort,
            turns=(Turn(role="user", blocks=(TextBlock(text=prompt),)),),
            max_output=args.max_output_bytes + 2000,
            max_text_output_bytes=args.max_output_bytes,
        )
        adapter: ModelClient = (
            ClaudeSubscriptionClient if claude else CodexSubscriptionClient
        )(
            client,
            args.attempt,
            allow_data_transfer=args.allow_data_transfer,
            allow_subscription_usage=args.allow_subscription_usage,
            timeout=args.timeout,
        )
        result = asyncio.run(adapter.complete(request))
        answer = result.turn.blocks[0]
        assert isinstance(answer, TextBlock)
        if args.json:
            print(
                json.dumps(
                    {
                        "provider": args.provider,
                        "requested_model": request.model,
                        "requested_effort": request.effort,
                        "answer": answer.text,
                        "usage": result.usage.model_dump(mode="json"),
                        "billing_verified": False,
                    }
                )
            )
        else:
            print(answer.text)
        return 0
    except (OSError, ValueError, ProviderError, UnicodeError):
        print(
            "Subscription request rejected or failed; inspect any retained receipt. "
            "Mos did not repeat the invocation.",
            file=sys.stderr,
        )
        return 2


def create_authorization(args: argparse.Namespace) -> int:
    import os
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from pydantic import TypeAdapter

    from mos_eisley.core.models import canonical_bytes
    from mos_eisley.providers.codex_subscription import write_receipt
    from mos_eisley.subscription_authorization import (
        SubscriptionAuthorization,
        SubscriptionGrant,
        SubscriptionProvider,
        executable_sha256,
        native_context_sha256,
    )
    from mos_eisley.subscription_usage import private_directory

    if not 1 <= args.valid_for_seconds <= 3600:
        raise ValueError("Subscription authority expiry must be 1–3600 seconds")
    grants: list[SubscriptionGrant] = []
    for role, provider, model, effort, client, calls in args.grant:
        selected_provider = TypeAdapter[SubscriptionProvider](
            SubscriptionProvider
        ).validate_python(provider)
        selected = select_client(Path(client))
        grants.append(
            SubscriptionGrant.model_validate_json(
                json.dumps(
                    {
                        "role": role,
                        "provider": selected_provider,
                        "model": model,
                        "effort": effort,
                        "client": str(selected),
                        "client_sha256": executable_sha256(selected),
                        "authentication_context_sha256": native_context_sha256(
                            selected_provider
                        ),
                        "max_invocations": int(calls),
                    }
                )
            )
        )
    authority = SubscriptionAuthorization(
        authorization_id=uuid4().hex,
        session_id=args.session_id,
        owner_uid=os.getuid(),
        workspace=args.workspace.resolve(strict=True),
        usage_root=args.usage_root.absolute(),
        valid_until=datetime.now(UTC) + timedelta(seconds=args.valid_for_seconds),
        grants=tuple(grants),
        max_invocations=args.max_invocations,
        max_input_bytes=args.max_input_bytes,
        max_output_bytes=args.max_output_bytes,
        max_output_tokens=args.max_output_tokens,
        timeout_seconds=args.timeout,
        allow_data_transfer=args.allow_data_transfer,
        allow_subscription_usage=args.allow_subscription_usage,
        accept_unverified_billing_and_native_retries=args.accept_unverified_billing_and_native_retries,
    )
    usage = private_directory(authority.usage_root)
    os.close(usage)
    output = args.output.absolute()
    parent = private_directory(output.parent)
    try:
        write_receipt(parent, output.name, json.loads(canonical_bytes(authority)))
    finally:
        os.close(parent)
    print(
        json.dumps(
            {
                "authorization_sha256": authority.sha256,
                "session_id": authority.session_id,
                "output": str(output),
                "billing_verified": False,
                "inference_invocations": 0,
            }
        )
    )
    return 0
