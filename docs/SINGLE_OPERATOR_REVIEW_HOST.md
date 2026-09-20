# One-process single-operator review host

`SingleOperatorReviewHost` supplies the one shared Joshua Myers signing identity and
late OpenAI credential callback required by ADR-0005. It is an owning-library boundary,
not a public live-review command. Construction generates one Ed25519 private key in
memory and performs no Keychain lookup, spending operation, worker start or provider
request.

## Keychain record

Create a generic-password item with a trusted macOS Keychain interface before starting
the ceremony:

- service: `mos-eisley.openai.review.v1`
- account: `joshua-myers`
- password: the project-scoped OpenAI API key

Do not put the password in a shell command, repository file, command argument or task
record. The adapter selects the native macOS backend directly rather than an
environment-selected keyring plugin. It reads the record only when the existing
credential callback is invoked after current admission and local approval. Every use
is a fresh, bounded read; the credential is not cached or copied into the environment.
Missing, malformed and backend failures return fixed diagnostics without the secret.
Deleting or changing the item revokes a later callback but cannot undo a request that
has already been sent.

## Owning-process composition

Create exactly one host and use its public signer in every schema-2 campaign, phase,
observation and launch policy. The host rejects a policy enrolled to another identity
or key even if that policy is otherwise valid.

```python
from datetime import UTC, datetime, timedelta

from mos_eisley.run.review_single_operator import (
    MacOSKeychainOpenAICredential,
    SingleOperatorReviewHost,
)

credential = MacOSKeychainOpenAICredential("joshua-myers")
with SingleOperatorReviewHost(credential) as operator:
    now = datetime.now(UTC)
    phase_policy = operator.authority_policy(
        policy_id="joshua-live-review",
        valid_from=now,
        valid_until=now + timedelta(minutes=10),
        max_authorization_seconds=60,
        max_reserved_microusd=5_000_000,
    )

    async def load_phase(scope):
        return await operator.authorize_phase(scope, phase_policy, lifetime_seconds=60)

    # Supply load_phase and operator.load_api_key to the existing probe.
    # Explicitly call operator.sign_observation(...) only after assessing the
    # completed runtime evidence, and operator.authorize_launch(...) only after
    # reviewing the accepted campaign and exact launch scope.
```

The phase authorization call grants only the exact current phase and still requires
the existing local approval. `sign_observation` requires an explicit confirmation that
the proposed runtime claims were self-reviewed. `authorize_launch` separately requires
explicit commitment-custody, credentialed-campaign and self-review-risk assertions.
Every produced phase and launch signature is immediately reverified before return.

Pass `operator.load_api_key` directly to `BrokeredReviewConformanceProbe`. Do not call
it during configuration, preview, campaign sealing, observation construction or launch
review. The probe already invokes it separately at count and generation boundaries and
rechecks admission after each retrieval.

## Lifecycle and limitations

The same host instance must remain alive from policy creation through all three fixed
campaign slots and the final exact launch decision. The private signing key has no
serialization API and is never written by this module. `close()` drops the process
reference and permanently rejects later signing or credential callbacks; a crash or
restart therefore leaves the fixed campaign incomplete and grants no retry.

Python and the cryptography backend do not promise physical memory zeroization. The
signing key and each retrieved API key necessarily exist briefly in trusted host
memory. Same-user process compromise, Keychain compromise and already-dispatched
requests remain residual risks. This host does not create policies on its own, inspect
the provider account's retention configuration, create ledgers, approve transfer
content, sign observations automatically, or activate review routing.

The separately approved default-retention assumptions and exact wire-field inventory
are recorded in [the live transfer review](LIVE_READ_ONLY_REVIEW_TRANSFER_REVIEW.md).
That record does not change this host's authority or make a Zero Data Retention claim.

Tests use a memory-only credential backend and synthetic provider transports. They
cover construction without credential access, uncached late reads, effective-user
changes, redacted errors, close/revocation, mixed-key rejection, explicit attestation,
signature verification, retained-file secret scanning and decline-before-Keychain.
They do not read a production Keychain item or call OpenAI.
