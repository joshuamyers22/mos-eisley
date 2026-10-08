"""Prepare or explicitly run one bounded synthetic Claude diagnostic invocation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from pydantic import JsonValue
from qualify_subscription_roles import write

from mos_eisley.conversation_subscription import AuthorizedSubscriptionClient
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import JsonSchemaOutput, ModelRequest, TextBlock, Turn
from mos_eisley.providers.codex_subscription import select_client
from mos_eisley.subscription_authorization import (
    SubscriptionAuthorization,
    SubscriptionGrant,
    executable_sha256,
    native_context_sha256,
    read_authorization,
)


def prepare(root: Path, client: Path) -> None:
    root.mkdir(mode=0o700, exist_ok=False)
    workspace, usage = root / "workspace", root / "usage"
    workspace.mkdir(mode=0o700)
    usage.mkdir(mode=0o700)
    client = select_client(client, name="claude")
    grant = SubscriptionGrant(
        role="critic_anthropic",
        provider="anthropic_subscription",
        model="claude-sonnet-5",
        effort="high",
        client=client,
        client_sha256=executable_sha256(client),
        authentication_context_sha256=native_context_sha256("anthropic_subscription"),
        max_invocations=1,
    )
    auth = SubscriptionAuthorization(
        authorization_id=uuid4().hex,
        session_id=uuid4().hex,
        owner_uid=os.getuid(),
        workspace=workspace.resolve(),
        usage_root=usage.resolve(),
        valid_until=datetime.now(UTC) + timedelta(seconds=1200),
        grants=(grant,),
        max_invocations=1,
        max_input_bytes=128000,
        max_output_bytes=16000,
        max_output_tokens=2048,
        timeout_seconds=60,
        allow_data_transfer=True,
        allow_subscription_usage=True,
        accept_unverified_billing_and_native_retries=True,
    )
    write(root / "authorization.json", json.loads(canonical_bytes(auth)))
    print(
        json.dumps(
            {
                "prepared_only": True,
                "authorization_sha256": auth.sha256,
                "max_invocations": 1,
            }
        )
    )


def read_scope(root: Path) -> SubscriptionAuthorization:
    auth = read_authorization(root / "authorization.json")
    auth.check_current((root / "workspace").resolve(), auth.session_id)
    grant = auth.grant("critic_anthropic")
    if (
        len(auth.grants) != 1
        or auth.max_invocations != 1
        or grant.max_invocations != 1
        or (grant.provider, grant.model, grant.effort)
        != ("anthropic_subscription", "claude-sonnet-5", "high")
        or auth.usage_root != (root / "usage").resolve()
        or (
            auth.max_input_bytes,
            auth.max_output_bytes,
            auth.max_output_tokens,
            auth.timeout_seconds,
        )
        != (128000, 16000, 2048, 60)
    ):
        raise ValueError(
            "Claude diagnostic scope differs from its one-invocation limits"
        )
    return auth


async def run(root: Path) -> dict[str, JsonValue]:
    auth = read_scope(root)
    write(
        root / "run-started.json",
        {"authorization_sha256": auth.sha256, "automatic_replay": False},
    )
    report: dict[str, JsonValue] = {
        "authorization_sha256": auth.sha256,
        "billing_verified": False,
    }
    request = ModelRequest(
        provider="anthropic_subscription",
        model="claude-sonnet-5",
        effort="high",
        turns=(
            Turn(
                role="user",
                blocks=(
                    TextBlock(
                        text='Synthetic qualification. Return exactly {"status":"ok"}.'
                    ),
                ),
            ),
        ),
        max_output=18000,
        max_text_output_bytes=16000,
        max_output_tokens=2048,
        response_format=JsonSchemaOutput(
            name="diagnostic",
            json_schema={
                "type": "object",
                "properties": {"status": {"type": "string", "enum": ["ok"]}},
                "required": ["status"],
                "additionalProperties": False,
            },
        ),
    )
    try:
        await AuthorizedSubscriptionClient(
            auth, root / "authorization.json", "critic_anthropic", "diagnostic-json"
        ).complete(request)
        report["result"] = "passed"
    except (Exception, asyncio.CancelledError) as error:
        report["result"] = "stopped_on_first_failure"
        report["failure_type"] = type(error).__name__
    slots = sorted(auth.usage_root.glob("*/slot-*"))
    report["reserved_invocations"] = len(slots)
    report["dispatch_markers"] = sum(
        (slot / "native/dispatch.json").exists() for slot in slots
    )
    if slots and (slots[-1] / "native/failure.json").exists():
        report["failure_metadata"] = json.loads(
            (slots[-1] / "native/failure.json").read_text()
        )
    write(root / "diagnostic.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--client", type=Path)
    parser.add_argument("--approve-live-claude-diagnostic", action="store_true")
    args = parser.parse_args()
    root = args.root.absolute()
    if args.action == "prepare":
        if args.client is None:
            parser.error("prepare requires an absolute Claude client")
        prepare(root, args.client)
    else:
        if not args.approve_live_claude_diagnostic:
            parser.error("run requires explicit one-invocation diagnostic approval")
        report = asyncio.run(run(root))
        print(json.dumps(report))
        if report["result"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
