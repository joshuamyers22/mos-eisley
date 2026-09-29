# Adversarial review: response-budget correction

## Review metadata

- Repository: Mos Eisley Memory Selection
- Remote: `https://github.com/joshuamyers22/mos-eisley.git`
- Branch and base commit: `feat/production-template-guidance` at
  `fed1e5d11349cc00a629467a168a4c0175cbba1b`
- Reviewer and date: Codex, 2026-09-20
- Product purpose: bounded, evidence-backed memory selection and review
- Runtime and framework: Python 3.12, Pydantic contracts, isolated broker workers
- First-party scope: response-budget policy, canonical protocol, model reviewer,
  brokered OpenAI adapter, launch/profile projection, focused tests and records
- Exclusions: live provider behavior, credentials, billing reconciliation, historical
  artifact mutation, and authorization of a replacement qualification campaign
- Pre-existing working-tree changes: the live-qualification and single-operator-host
  changes listed in `notes/REVIEW_RESPONSE_BUDGET_FIX.md` were preserved
- North star: G2, Q-004, `docs/AGENTIC_VERIFICATION_GUIDE.md`, and the current
  Python/threat-model/incident guidance
- Blocking threshold: uncontrolled bytes or spend, mutable request authority,
  historical evidence reinterpretation, retry, credential access, or failed gates
- Independence: self-review under Joshua Myers's approved single-operator contract;
  automated boundaries and exact retained-shape replay support but do not create an
  independent-human-review claim
- Review ceiling: three evidence-changing passes, one full gate, one container gate;
  stop when a distinct adversarial pass finds no blocker

## Executive verdict

- Overall grade: A-
- Release recommendation: approve this offline correction; no live qualification or
  launch approval follows
- Highest risk attacked: increasing the whole response envelope could accidentally
  admit unbounded visible prose or increase provider/spending authority
- Strongest property: the text, canonical-envelope and token limits are distinct,
  frozen into the canonical request, and enforced by both reviewer and broker
- Recommended first improvement: none unless a gate or new evidence falsifies the
  corrected contract

## Verification evidence

| Check | Command/evidence | Result | Notes |
|---|---|---|---|
| Formatting/lint | focused Ruff plus `make check` | Pass | Full repository lint/format gate passed |
| Static typing | Pyright | Pass | Initial narrowing findings corrected; zero errors on rerun |
| Focused tests | protocol, reviewer, broker, launch suites | Pass | Exact and one-byte-over limits plus opaque-reasoning case |
| Broad affected tests | review/provider/protocol discovery commands | Pass | 422 tests |
| Production-like replay | two exact retained response shapes, offline | Pass | 8,617/4,243 and 8,221/2,680 canonical/text bytes |
| Full tests/coverage/package | `make check` | Pass | 2,451 source tests (4 skipped), 89% coverage, exports/builds, 1,842 installed-wheel tests |
| Container architecture | `make container` | Pass after one fixture correction | Image/CLI, isolation and all review smoke gates passed |
| Financial boundary | request/spend assertions and diff inspection | Pass | 4,096-token ceiling and pricing/reservations unchanged |

## Architecture map

- Domain policy: `BudgetPolicy`, `Budget`, `ModelRequest`, and model registry limits
- Application use case: `ModelReviewer` projects and parses one critic/judge exchange
- Port: `ModelClient`
- Infrastructure adapter: `BrokeredOpenAIClient` and isolated request-bound broker
- Delivery/composition: `ReviewLaunchConfiguration` and preview/admission flow
- External system: OpenAI Responses, not contacted by this correction
- Dependency direction: launch and broker adapters depend inward on canonical policy;
  no vendor type enters the budget or reviewer contracts

## Findings and disposition

### Resolved: the original 4,000-byte visible-answer assumption was false

- Location: retained final-campaign response shapes and
  `src/mos_eisley/run/review_launch.py:61`
- Principle: correctness, evidence before policy
- Evidence: one valid JSON answer was 4,243 UTF-8 bytes
- Failure mode: a separate envelope alone would still reject that valid response
- Correction: bind an explicit 8,000-byte answer cap and 64,000-byte canonical
  envelope while preserving the 4,096-token/spend ceiling
- Acceptance: both exact retained shapes and synthetic boundaries pass offline
- Status: closed

### Resolved: defaults must not be invisible to launch authorization

- Location: `src/mos_eisley/core/budget.py:19` and
  `src/mos_eisley/run/review_launch.py:61`
- Principle: explicit side effects and immutable authorization
- Evidence: excluding new default fields would let configuration bytes omit a limit
  that changes request behavior
- Failure mode: a reviewed configuration could rely on an unsealed implicit default
- Correction: serialize the reviewed launch text and envelope settings explicitly;
  the resulting request also binds both limits in its hash
- Acceptance: launch-preview tests inspect both canonical configuration and request
- Status: closed

No open critical, high, medium, or low finding remains in the scoped diff. The
historical Q-004 campaign finding remains immutable even though current code is fixed.

## Clean-code and architecture assessment

- Names distinguish visible text (`max_text_output_bytes`) from the whole canonical
  response (`max_output` / `response_envelope_bytes`).
- Pure budget resolution remains independent of provider, filesystem and transport.
- The reviewer owns role projection/parsing; the broker independently rechecks the
  frozen limits before retaining a successful completion.
- No retry, fallback, migration, credential read or provider dispatch was added.
- Optional protocol/profile decoding preserves old artifact readability; new launch
  configurations and requests bind the corrected values explicitly.
- Tests are synthetic or read-only replay and contain no captured provider content.
- The first container pass falsified completeness of the test-fixture migration: the
  isolation smoke manually built a brokered request without the required text cap.
  Adding its pre-existing 4,000-byte intent closed the omission without weakening the
  broker; the complete container gate is rerun rather than counting the partial pass.

## Metrics and smell inventory

- Scoped production modules: 5 primary modules, 947 lines total
- Broad exception handlers: the existing reviewer boundary converts one-role failures
  to coarse `ProviderError`; deterministic parsing occurs inside that boundary
- Import cycles and new concrete inward dependencies: none observed
- Suppressed lint/type findings: none
- Environment dependency: the full MCP suite requires localhost socket binding;
  the unrestricted gate is the recorded production-template path

## Improvement plan

| Priority | Change | Finding addressed | Owner | Verification | Status |
|---:|---|---|---|---|---|
| 1 | Complete full and container gates | Release evidence | Josh Myers | `make check`; `make container` | Complete |

## Final challenge answers

1. The hardest rule is exact broker/request/evidence identity; existing pure projections
   and hash checks test it without live infrastructure.
2. `ModelReviewer` owns related request and parse responsibilities for one exchange;
   no unrelated responsibility was added.
3. The broad role boundary deliberately returns a coarse provider error and cannot
   turn malformed output into valid evidence.
4. No concrete provider dependency points into budget or protocol policy.
5. Replacing OpenAI affects the adapter and registry, not the independent byte rules.
6. The private-shape replay is machine-local, so synthetic exact-boundary tests are the
   durable regression evidence.
7. The smallest safe correction was two independently enforced, request-bound limits.
8. Wire allocation remains the outer limit; an over-limit response fails closed and is
   never retried.
9. Exact retained text measurement changed the design from 4,000 to 8,000 bytes.
10. The loop met its pass and diminishing-return rules after the full and corrected
    container gates passed with no open finding.
