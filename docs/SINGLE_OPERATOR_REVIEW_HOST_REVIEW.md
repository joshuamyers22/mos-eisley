# Adversarial review: single-operator review host

## Review metadata

- Repository: Mos Eisley
- Branch and starting commit: `feat/production-template-guidance` from
  `fed1e5d11349cc00a629467a168a4c0175cbba1b`
- Reviewer: Codex; accountable governance approval by Joshua Myers
- Review date: 2026-09-20
- Product purpose: one-process custody for the already-approved single-operator
  live read-only review
- First-party scope: `review_single_operator.py`, its focused tests, operating guide,
  and the existing phase/observation/launch contracts it composes
- Exclusions: real Keychain contents, provider account settings, live prompts, funded
  ledgers, provider transport, and any live request
- Requirement and north star: create one ephemeral Joshua Myers Ed25519 identity and
  retrieve one named OpenAI credential only at an admitted provider edge
- Rubric: the live-qualification verification and threat-model records; any private-key
  persistence, eager/cached credential read, signer substitution, secret-bearing error,
  public live CLI, or provider call blocks acceptance
- Context and ceiling: this is not an independent review; synthetic providers and
  credentials only, zero provider spend, stop after focused, broader-review, full, and
  immutable-image gates

## Executive verdict

- Overall grade: approve with operational follow-up
- Release recommendation: approve the inert library boundary; do not infer live launch
  readiness
- Highest risk: Joshua's process and login session become the shared failure domain for
  signing identity, human judgment, and Keychain access
- Strongest property: construction is inert with respect to the credential, and every
  signing operation rebinds the exact shared public identity to an existing validated
  contract
- Recommended first improvement: validate the named Keychain item, provider-account
  retention setting, and exact transfer payload without creating a public launch CLI

## Verification evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Formatting/lint | focused Ruff commands | Passed | New module, tests, and guide |
| Static typing | focused Pyright command | Passed | 0 errors |
| Focused behavior | focused `unittest` command | Passed | 9 synthetic tests |
| Review regression | `python -m unittest discover -s tests -p 'test_review_*.py'` | Passed | 356 tests in 355.666 seconds |
| Full quality gate | `make check` | Passed | 2,446 source tests, 4 skipped, 89% coverage; export/build and 1,839 wheel tests passed |
| Immutable image | `make container` | Passed | Offline suite; image `sha256:42aac38dc474addd64eec136fc20a33a84fee7534533bbc7645f74be37860f4c` |
| Live/provider | Not run | Intentionally excluded | No credential read, reservation, spend, or request |

## Architecture map

- Domain policy: existing schema-2 single-operator policies and signed artifacts remain
  authoritative.
- Application boundary: `SingleOperatorReviewHost` generates one key, constructs exact
  policies, and signs only after explicit assertions.
- Infrastructure adapter: `MacOSKeychainOpenAICredential` directly selects the native
  macOS backend and performs a fresh, owner-bound read per callback.
- Delivery mechanism: none; the host is an owning-library composition boundary.
- External systems: macOS Keychain and the existing brokered provider boundary.
- Dependency flow: host infrastructure composes existing application/domain contracts;
  those contracts do not import Keychain or provider SDK types.

## Findings

### Accepted high: one process is the common trust and compromise domain

- Location: `SingleOperatorReviewHost`
- Evidence: one in-memory private key signs authority, observation, and launch artifacts,
  while the same effective user may access the named Keychain item
- Failure mode: process compromise or operator error can affect every human assertion
- Why tests do or do not protect it: tests prove identity consistency and fail-closed
  substitution behavior, but cannot create independent human judgment
- Disposition: explicitly accepted by Joshua Myers under ADR-0005 and encoded as
  `single_operator`; never represent the resulting evidence as independent review
- Reconsideration: higher spend, automation, multi-user use, or an available independent
  reviewer

### Accepted medium: Python cannot guarantee private-key zeroization

- Location: `SingleOperatorReviewHost.close`
- Evidence: close drops the sole application reference, but immutable allocator/runtime
  copies cannot be physically wiped by this code
- Failure mode: advanced process-memory or crash-dump access could recover key material
- Correction and acceptance: keep the key process-local, never serialize it, close the
  host on every exit, do not retry after process loss, and document the limitation
- Verification: close-path tests reject later signing and credential callbacks

### Operational follow-up: the real Keychain and account settings remain unverified

- Location: production environment outside the repository
- Evidence: all tests inject an in-memory backend; the real secret was intentionally not
  accessed
- Consequence: library correctness does not prove that the named item exists, its ACL is
  appropriate, or the provider account has the intended retention control
- Acceptance criteria: Joshua creates/reviews the exact generic-password record in the
  trusted Keychain UI, then reviews account retention and the exact transfer payload
  before any credential callback

## Clean code and architecture disposition

Names expose custody and operator intent. Credential access is behind a minimal port,
time and key generation are injectable, and fixed errors do not preserve backend or
secret text. Provider calls, ledgers, campaign ownership, retries, and presentation stay
outside this module. The host intentionally repeats exact-policy validation at each
signing edge so a caller cannot mix another single-operator key into the ceremony.

## Improvement plan

| Priority | Change | Owner | Verification | Status |
|---:|---|---|---|---|
| 1 | Run complete repository and immutable-image gates | Codex | `make check`; `make container` | Complete |
| 2 | Create and inspect the named Keychain item without exposing its value | Joshua Myers | Trusted local prompt and metadata-only review | Complete |
| 3 | Review account retention and exact provider payload | Joshua Myers | Recorded exact operational review | Complete; default retention accepted, exact live previews still require hash approval |
| 4 | Prefer schema-1 separated mode when another reviewer is available | Joshua Myers | Disjoint signer policies | Future |

## Final challenge answers

The hardest rule remains meaningful human assessment: a signature authenticates a key,
not attention or independence. The credible new bypasses were eager secret access,
backend selection through ambient configuration, signer replacement, and retained
secret-bearing diagnostics; the adapter and focused tests close those paths. The
machine-dependent real-Keychain path is deliberately an operational acceptance check,
not a mocked production claim. No live provider, retry, deadline, ledger, or spending
path was added. The complete gates passed after one transient fixture miss was reproduced
successfully in isolation and a clean full rerun. The next distinct evidence must come
from the real operational inputs; repeated local self-review without changed evidence
meets the stop rule.
