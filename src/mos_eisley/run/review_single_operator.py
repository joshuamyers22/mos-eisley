"""One-process custody for an explicitly accepted single-operator review.

This module owns no campaign, approval UI, spending ledger, worker, or provider
transport.  It supplies the shared public identity, explicit signing operations and
the late credential callback required by those existing boundaries.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    ReviewConformanceScope,
    ReviewConformanceSigner,
    SignedReviewConformanceAuthorization,
    make_review_conformance_authorization,
    review_conformance_signer,
    sign_review_conformance_authorization,
    verify_review_conformance_authorization,
)
from mos_eisley.run.review_conformance_observation import (
    ReviewProbeObservation,
    SignedReviewProbeObservation,
    sign_review_probe_observation,
)
from mos_eisley.run.review_launch_authorization import (
    ReviewLaunchAuthorityPolicy,
    ReviewLaunchDecision,
    ReviewLaunchScope,
    SignedReviewLaunchDecision,
    sign_review_launch_decision,
    verify_review_launch_decision,
)


class ReviewOperatorFailure(ValueError):
    """Safe operator diagnostic that must never contain credential material."""


class CredentialBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...


def _label(value: str, field: str) -> str:
    if (
        not 1 <= len(value) <= 255
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"review credential {field} is invalid")
    return value


def _macos_keychain() -> CredentialBackend:
    if sys.platform != "darwin":
        raise ReviewOperatorFailure("review credential requires macOS Keychain")
    try:
        from keyring.backends.macOS import Keyring

        return cast(CredentialBackend, Keyring())
    except Exception:
        raise ReviewOperatorFailure(
            "review credential keychain is unavailable"
        ) from None


class MacOSKeychainOpenAICredential:
    """Read one named API key without caching it or changing the environment."""

    default_service = "mos-eisley.openai.review.v1"

    def __init__(
        self,
        account: str,
        *,
        service: str = default_service,
        backend: CredentialBackend | None = None,
    ) -> None:
        self._service = _label(service, "service")
        self._account = _label(account, "account")
        self._owner = os.geteuid()
        self._backend = _macos_keychain() if backend is None else backend

    def __repr__(self) -> str:
        return f"{type(self).__name__}(service={self._service!r}, account='[redacted]')"

    def load(self) -> str:
        """Return the current keychain value; callers own its short-lived use."""
        if os.geteuid() != self._owner:
            raise ReviewOperatorFailure("review credential owner changed")
        try:
            value = self._backend.get_password(self._service, self._account)
        except Exception:
            raise ReviewOperatorFailure(
                "review credential keychain is unavailable"
            ) from None
        if (
            value is None
            or not 8 <= len(value) <= 4096
            or value != value.strip()
            or any(character in value for character in ("\x00", "\r", "\n"))
        ):
            raise ReviewOperatorFailure(
                "review credential is missing or invalid"
            ) from None
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            raise ReviewOperatorFailure(
                "review credential is missing or invalid"
            ) from None
        return value


def _now() -> datetime:
    return datetime.now(UTC)


class SingleOperatorReviewHost:
    """Hold one ephemeral signing key for one explicit owning-process ceremony."""

    def __init__(
        self,
        credential: MacOSKeychainOpenAICredential,
        *,
        signer_id: str = "joshua-myers",
        clock: Callable[[], datetime] = _now,
        key_factory: Callable[[], Ed25519PrivateKey] = Ed25519PrivateKey.generate,
    ) -> None:
        self._owner = os.geteuid()
        self._credential = credential
        self._clock = clock
        self._key: Ed25519PrivateKey | None = key_factory()
        self._signer = review_conformance_signer(signer_id, self._key.public_key())

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(signer_id={self._signer.signer_id!r}, "
            f"public_key_sha256={self._signer.key_sha256!r}, closed={self.closed})"
        )

    def __enter__(self) -> SingleOperatorReviewHost:
        self._active()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def closed(self) -> bool:
        return self._key is None

    @property
    def signer(self) -> ReviewConformanceSigner:
        self._active()
        return self._signer

    def _active(self) -> Ed25519PrivateKey:
        if os.geteuid() != self._owner:
            raise ReviewOperatorFailure("review operator owner changed")
        if self._key is None:
            raise ReviewOperatorFailure("review operator host is closed")
        return self._key

    def close(self) -> None:
        """Drop the process reference; Python cannot promise physical zeroization."""
        self._key = None

    def _phase_policy(
        self, policy: ReviewConformanceAuthorityPolicy
    ) -> ReviewConformanceAuthorityPolicy:
        if (
            policy.operator_mode != "single_operator"
            or policy.authorities != (self.signer,)
            or policy.observers != (self.signer,)
        ):
            raise ReviewOperatorFailure(
                "review authority policy differs from the owning operator"
            )
        return policy

    def _launch_policy(
        self, policy: ReviewLaunchAuthorityPolicy
    ) -> ReviewLaunchAuthorityPolicy:
        if policy.operator_mode != "single_operator" or policy.reviewers != (
            self.signer,
        ):
            raise ReviewOperatorFailure(
                "review launch policy differs from the owning operator"
            )
        return policy

    def load_api_key(self) -> str:
        """Late callback for the existing probe's post-admission credential edge."""
        self._active()
        return self._credential.load()

    def authority_policy(
        self,
        *,
        policy_id: str,
        valid_from: datetime,
        valid_until: datetime,
        max_authorization_seconds: int,
        max_reserved_microusd: int,
    ) -> ReviewConformanceAuthorityPolicy:
        signer = self.signer
        return ReviewConformanceAuthorityPolicy(
            schema_version=2,
            operator_mode="single_operator",
            policy_id=policy_id,
            authorities=(signer,),
            observers=(signer,),
            valid_from=valid_from,
            valid_until=valid_until,
            max_authorization_seconds=max_authorization_seconds,
            max_reserved_microusd=max_reserved_microusd,
        )

    def launch_policy(
        self,
        *,
        policy_id: str,
        valid_from: datetime,
        valid_until: datetime,
        max_decision_seconds: int,
        max_reserved_microusd: int,
    ) -> ReviewLaunchAuthorityPolicy:
        return ReviewLaunchAuthorityPolicy(
            schema_version=2,
            operator_mode="single_operator",
            policy_id=policy_id,
            reviewers=(self.signer,),
            valid_from=valid_from,
            valid_until=valid_until,
            max_decision_seconds=max_decision_seconds,
            max_reserved_microusd=max_reserved_microusd,
        )

    async def authorize_phase(
        self,
        scope: ReviewConformanceScope,
        policy: ReviewConformanceAuthorityPolicy,
        *,
        lifetime_seconds: int,
    ) -> SignedReviewConformanceAuthorization:
        key = self._active()
        policy = self._phase_policy(policy)
        now = self._clock()
        authorization = make_review_conformance_authorization(
            scope,
            policy,
            now,
            min(
                now + timedelta(seconds=lifetime_seconds),
                policy.valid_until,
                scope.expires_at,
            ),
        )
        signed = sign_review_conformance_authorization(
            authorization, self._signer.signer_id, key
        )
        verify_review_conformance_authorization(signed, policy, scope, now)
        return signed

    def sign_observation(
        self,
        observation: ReviewProbeObservation,
        policy: ReviewConformanceAuthorityPolicy,
        *,
        claims_reviewed: bool,
    ) -> SignedReviewProbeObservation:
        if claims_reviewed is not True:
            raise ReviewOperatorFailure(
                "review observation requires explicit self-assessment"
            )
        policy = self._phase_policy(policy)
        if (
            observation.schema_version != 2
            or observation.operator_mode != "single_operator"
            or observation.authority_policy_sha256 != policy.sha256
        ):
            raise ReviewOperatorFailure(
                "review observation differs from the owning operator policy"
            )
        return sign_review_probe_observation(
            observation, self._signer.signer_id, self._active()
        )

    def authorize_launch(
        self,
        scope: ReviewLaunchScope,
        policy: ReviewLaunchAuthorityPolicy,
        *,
        lifetime_seconds: int,
        commitment_custody_reviewed: bool,
        credentialed_campaign_reviewed: bool,
        self_review_risk_accepted: bool,
    ) -> SignedReviewLaunchDecision:
        if not (
            commitment_custody_reviewed is True
            and credentialed_campaign_reviewed is True
            and self_review_risk_accepted is True
        ):
            raise ReviewOperatorFailure(
                "review launch requires every single-operator assertion"
            )
        key = self._active()
        policy = self._launch_policy(policy)
        now = self._clock()
        decision = ReviewLaunchDecision(
            schema_version=2,
            operator_mode="single_operator",
            scope=scope,
            issued_at=now,
            valid_until=min(
                now + timedelta(seconds=lifetime_seconds),
                policy.valid_until,
                scope.expires_at,
            ),
            commitment_custody_reviewed=True,
            credentialed_campaign_reviewed=True,
            single_operator_self_review_risk_accepted=True,
        )
        signed = sign_review_launch_decision(decision, self._signer.signer_id, key)
        verify_review_launch_decision(signed, policy, scope, now)
        return signed
