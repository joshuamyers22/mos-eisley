"""Immutable local subscription authority, distinct from API spending policies."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.protocol import Effort
from mos_eisley.core.registry import ModelRegistry, ModelSpec

SubscriptionProvider = Literal["openai_subscription", "anthropic_subscription"]
SubscriptionRole = Literal[
    "chat", "creator", "child", "critic_openai", "critic_anthropic", "judge"
]


def provider_family(provider: str) -> str:
    if provider in {"openai", "openai_subscription"}:
        return "openai"
    if provider in {"anthropic", "anthropic_subscription"}:
        return "anthropic"
    raise ValueError("Unknown provider family")


def subscription_registry() -> ModelRegistry:
    """Explicit native compatibility candidates; role qualification is separate."""
    profiles: tuple[tuple[str, str, tuple[Effort, ...]], ...] = (
        ("openai_subscription", "gpt-6-sol", ("medium",)),
        ("openai_subscription", "gpt-6-astra", ("medium",)),
        ("openai_subscription", "gpt-5.6-terra", ("medium",)),
        ("anthropic_subscription", "claude-sonnet-5", ("high",)),
        ("anthropic_subscription", "claude-opus-5-5", ("medium",)),
    )
    return ModelRegistry(
        models=tuple(
            ModelSpec(
                provider=provider,
                id=model,
                context_bytes=192_000,
                max_output_bytes=64_000,
                # Local acceptance ceilings; native generation/billing is unverified.
                context_tokens=128_000,
                max_output_tokens=8192,
                efforts=efforts,
                default_effort=efforts[0],
                tool_calling=False,
                structured_output=True,
                verification="fixture",
            )
            for provider, model, efforts in profiles
        )
    )


def native_context_sha256(provider: SubscriptionProvider) -> str:
    """Bind auth location, never read credentials or claim remote account identity."""
    home = Path.home().resolve()
    location = (
        Path(os.environ.get("CODEX_HOME", str(home / ".codex"))).resolve()
        if provider == "openai_subscription"
        else home / ".claude"
    )
    return digest((str(home) + "\n" + str(location)).encode())


def executable_sha256(path: Path) -> str:
    # Native binaries are larger than ordinary input files; stream bounded bytes.
    import hashlib
    import stat

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 256_000_000:
            raise ValueError("Native executable is inadmissible")
        checksum, count = hashlib.sha256(), 0
        while part := os.read(fd, 128_000):
            count += len(part)
            if count > 256_000_000:
                raise ValueError("Native executable exceeds its bound")
            checksum.update(part)
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or count != before.st_size:
            raise ValueError("Native executable changed")
        return checksum.hexdigest()
    finally:
        os.close(fd)


class SubscriptionGrant(Contract):
    role: SubscriptionRole
    provider: SubscriptionProvider
    model: str
    effort: Effort
    client: Path
    client_sha256: Digest
    authentication_context_sha256: Digest
    max_invocations: Annotated[int, Field(ge=1, le=64)]

    @model_validator(mode="after")
    def exact_route(self) -> Self:
        if not self.client.is_absolute():
            raise ValueError("Subscription client must be absolute")
        resolved = subscription_registry().resolve(
            self.provider, self.model, self.effort
        )
        if resolved.substituted:
            raise ValueError("Subscription route cannot substitute effort")
        if self.role.startswith("critic_") and self.role != "critic_" + provider_family(
            self.provider
        ):
            raise ValueError("Critic role must match its provider family")
        return self


class SubscriptionAuthorization(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["owner_subscription_usage"] = "owner_subscription_usage"
    authorization_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Path
    usage_root: Path
    valid_until: datetime
    grants: Annotated[tuple[SubscriptionGrant, ...], Field(min_length=1, max_length=6)]
    max_invocations: Annotated[int, Field(ge=1, le=64)]
    max_input_bytes: Annotated[int, Field(ge=1, le=128_000)]
    max_output_bytes: Annotated[int, Field(ge=1, le=64_000)]
    max_output_tokens: Annotated[int, Field(ge=1, le=8192)]
    timeout_seconds: Annotated[int, Field(ge=1, le=120)]
    allow_data_transfer: Literal[True]
    allow_subscription_usage: Literal[True]
    accept_unverified_billing_and_native_retries: Literal[True]

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if (
            not self.workspace.is_absolute()
            or not self.usage_root.is_absolute()
            or self.valid_until.tzinfo is None
        ):
            raise ValueError(
                "Subscription authority requires absolute paths and zoned expiry"
            )
        if any(grant.client.is_relative_to(self.workspace) for grant in self.grants):
            raise ValueError(
                "Subscription native clients cannot come from the selected workspace"
            )
        if len({g.role for g in self.grants}) != len(self.grants):
            raise ValueError("Subscription role grants must be unique")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, workspace: Path, session_id: str) -> None:
        if (
            datetime.now(UTC) >= self.valid_until
            or os.getuid() != self.owner_uid
            or workspace.resolve() != self.workspace
            or self.workspace.resolve() != self.workspace
            or session_id != self.session_id
        ):
            raise ValueError(
                "Subscription authorization expired or changed owner/workspace/session"
            )

    def grant(self, role: SubscriptionRole) -> SubscriptionGrant:
        selected = next((g for g in self.grants if g.role == role), None)
        if selected is None:
            raise ValueError("Subscription role is not authorized")
        return selected


def read_authorization(
    path: Path, expected_sha256: str | None = None
) -> SubscriptionAuthorization:
    import json

    from mos_eisley.conversation_memory_replace import unique_object
    from mos_eisley.subscription_usage import check_private, private_directory

    parent = private_directory(path.absolute().parent)
    fd = None
    try:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        check_private(fd, directory=False)
        before = os.fstat(fd)
        raw = os.read(fd, 32_001)
        after = os.fstat(fd)
        if (
            len(raw) > 32_000
            or len(raw) != before.st_size
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            raise ValueError("Subscription authorization changed or exceeds its bound")
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)
    json.loads(raw, object_pairs_hook=unique_object)
    result = SubscriptionAuthorization.model_validate_json(raw)
    if expected_sha256 is not None and result.sha256 != expected_sha256:
        raise ValueError("Subscription authorization changed")
    return result
