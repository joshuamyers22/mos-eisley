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
    PROVIDER,
    CodexSubscriptionClient,
    select_client,
    status,
)


def add_command(add_parser: Callable[..., argparse.ArgumentParser]) -> None:
    command = add_parser(
        "subscription", help="Explicit local ChatGPT subscription route"
    )
    actions = command.add_subparsers(dest="subscription_action", required=True)
    for action in ("status", "ask"):
        selected = actions.add_parser(action)
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
                "The compatible profile is gpt-6-sol with medium effort. "
                "Saved conversational coding and role qualification remain separate."
            )


def run_command(args: argparse.Namespace) -> int:
    try:
        if args.subscription_action == "ask" and (
            not args.allow_data_transfer or not args.allow_subscription_usage
        ):
            raise ValueError("Transfer and subscription-use consent are both required")
        client = select_client(args.client)
        if args.subscription_action == "status":
            result = asyncio.run(status(client))
            print(
                json.dumps(
                    {
                        "provider": PROVIDER,
                        "required_client_version": CLIENT_VERSION,
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
            provider=PROVIDER,
            model=args.model,
            effort=args.effort,
            turns=(Turn(role="user", blocks=(TextBlock(text=prompt),)),),
            max_output=args.max_output_bytes + 2000,
            max_text_output_bytes=args.max_output_bytes,
        )
        adapter = CodexSubscriptionClient(
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
                        "provider": PROVIDER,
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
