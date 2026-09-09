"""Operator-selected OAuth identity and scopes; no inline credentials."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract


class MCPOAuthSettings(Contract):
    issuer: Annotated[str, Field(min_length=1, max_length=4096)]
    client_id: Annotated[str, Field(min_length=1, max_length=1024)]
    account: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    registration: Literal["pre_registered"] = "pre_registered"
    scopes: Annotated[tuple[str, ...], Field(max_length=32)]
    callback_port: Annotated[int, Field(ge=1024, le=65535)] = 8765
    login_timeout_seconds: Annotated[int, Field(ge=5, le=600)] = 180
    allowed_auth_origins: Annotated[tuple[str, ...], Field(max_length=8)] = ()

    @model_validator(mode="after")
    def valid_scopes(self) -> Self:
        if len(set(self.scopes)) != len(self.scopes) or any(
            not scope
            or len(scope) > 256
            or any(ord(c) < 33 or ord(c) > 126 or c in '\\"' for c in scope)
            for scope in self.scopes
        ):
            raise ValueError("invalid OAuth scopes")
        if any(ord(c) < 32 for c in self.client_id):
            raise ValueError("invalid OAuth client identifier")
        return self

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.callback_port}/oauth/callback"
