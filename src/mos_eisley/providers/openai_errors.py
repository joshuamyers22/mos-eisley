"""Coarse OpenAI SDK error classification safe for durable diagnostics."""

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from mos_eisley.core.ports import ProviderFailureKind


def safe_openai_failure_kind(error: OpenAIError) -> ProviderFailureKind:
    """Map SDK exception types without retaining messages, bodies, or headers."""

    if isinstance(error, AuthenticationError):
        return "authentication_error"
    if isinstance(error, PermissionDeniedError):
        return "permission_error"
    if isinstance(error, RateLimitError):
        return (
            "quota_error"
            if getattr(error, "code", None) == "insufficient_quota"
            else "rate_limit_error"
        )
    if isinstance(error, NotFoundError):
        return "not_found_error"
    if isinstance(error, BadRequestError):
        return "invalid_request_error"
    if isinstance(error, APITimeoutError):
        return "provider_timeout"
    if isinstance(error, APIConnectionError):
        return "transport_error"
    return "provider_error"
