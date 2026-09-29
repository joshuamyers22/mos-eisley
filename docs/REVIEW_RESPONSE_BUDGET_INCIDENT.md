# Incident Review: final-campaign response-budget mismatch

- Date, duration, severity, owner: 2026-09-20; attempt-1 critic phase; high; Josh Myers
- User, data, and business impact: two paid critic responses were unusable, verified
  quorum failed, the final qualification exception was consumed, and production launch
  remained unauthorized. No secret disclosure, write action or retry occurred.
- Detection, mitigation, and current risk: retained completion receipts and controller
  quorum verification detected the mismatch and failed closed. Both containers were
  removed and later phases stopped. The code correction passed focused, full-package
  and complete container gates; no new campaign is authorized.

| Time with timezone | Evidence/event | Decision/action |
|---|---|---|
| 2026-09-20 13:43 UTC | Two OpenAI critic responses completed and settled locally | Retain exact evidence and continue local verification |
| 2026-09-20 13:43 UTC | Canonical sizes 8,221 and 8,617 exceeded the sealed 4,000-byte limit | Mark both completions failed; reject critic quorum |
| 2026-09-20 13:44 UTC | Controller terminated failed and both containers were removed | Consume the single-use exception and prohibit continuation/replacement |
| 2026-09-20 | Source trace found that one limit covered visible JSON and opaque encrypted reasoning | Authorize an offline contract correction with no provider access |

Trigger: low-effort `BudgetPolicy.reserve_low_bytes` was assigned directly to the
canonical `ModelRequest.max_output` ceiling while the OpenAI adapter retained opaque
encrypted reasoning in the same canonical response.

Contributing conditions: the provider token ceiling and local byte ceiling were
independently configured; tests proved oversized opaque reasoning failed but did not
include the positive case where visible JSON was small and only the opaque envelope
exceeded the answer reserve.

Exact retained-shape inspection also found that one valid visible JSON answer was
4,243 bytes. The corrected profile therefore binds an 8,000-byte UTF-8 text cap and a
separate 64,000-byte canonical-response envelope while retaining the existing
4,096-token and financial ceilings.

Control behavior: request identity, broker bounds, model-completion receipts, quorum,
no-retry accounting and cleanup all behaved as designed. The missing control was a
separate bounded canonical-envelope budget.

Systemic corrective action: separate visible-answer bytes from canonical-envelope
bytes in the pure budget contract; bind the envelope to the request; add exact boundary
tests and a synthetic retained-response-shape regression. Owner: Josh Myers. Due:
before any future live qualification proposal.
