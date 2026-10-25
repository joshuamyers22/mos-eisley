"""Host-only typed credential references and native-store resolution.

No repository configuration, agent payload or environment selects this store.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, model_validator

from mos_eisley.core.models import Contract, Identifier, canonical_bytes, digest
from mos_eisley.tools.mcp_oauth_store import CredentialBackend, credential_backend

SERVICE = "mos-eisley.network-attachment.v1"


class CredentialBoundaryError(ValueError):
    """Fixed diagnostic suitable for callers; never wrap native exception text."""


class CredentialRef(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["native_keychain"] = "native_keychain"
    owner_uid: Annotated[int, Field(ge=0)]
    name: Identifier

    @property
    def account(self) -> str:
        return digest(canonical_bytes(self))


class NetworkCredential(Contract):
    """Native-store value, never a transcript/event/replay contract."""

    schema_version: Literal[1] = 1
    reference: CredentialRef
    generation: Identifier
    endpoint_id: Identifier
    operations: tuple[Identifier, ...] = Field(min_length=1, max_length=8)
    expires_at: datetime
    secret: SecretStr = Field(repr=False)

    @model_validator(mode="after")
    def valid_secret(self) -> Self:
        if (
            self.expires_at.tzinfo is None
            or not re.fullmatch(
                r"[A-Za-z0-9._~+/=-]{8,4096}", self.secret.get_secret_value()
            )
            or len(set(self.operations)) != len(self.operations)
        ):
            raise ValueError("invalid network credential")
        return self


class NativeNetworkCredentials:
    """Read afresh at the socket write boundary; no session credential cache.

    Provision/rotate via the trusted native-store administrator, using a fresh
    generation for every replacement. Absence is revocation. The store itself is
    the authority; references do not grant access across OS owners.
    """

    def __init__(self, *, backend: CredentialBackend | None = None) -> None:
        self._backend = backend
        self.owner_uid = os.geteuid()

    def check_owner(self, reference: CredentialRef) -> None:
        if (
            os.getuid() != self.owner_uid
            or os.geteuid() != self.owner_uid
            or reference.owner_uid != self.owner_uid
        ):
            raise CredentialBoundaryError("Network credential owner unavailable")

    def resolve(
        self, reference: CredentialRef, endpoint_id: str, operation: str
    ) -> NetworkCredential:
        failed = False
        record: NetworkCredential | None = None
        try:
            self.check_owner(reference)
            backend = self._backend or credential_backend()
            raw = backend.get_password(SERVICE, reference.account)
            if raw is None or len(raw.encode("utf-8")) > 16_384:
                raise ValueError("record")
            record = NetworkCredential.model_validate_json(raw)
            if (
                record.reference != reference
                or record.endpoint_id != endpoint_id
                or operation not in record.operations
                or datetime.now(UTC) >= record.expires_at
            ):
                raise ValueError("scope")
        except Exception:
            failed = True
        if failed or record is None:
            raise CredentialBoundaryError("Network credential unavailable")
        return record
