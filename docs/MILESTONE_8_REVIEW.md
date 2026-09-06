# OpenAI spending-control adversarial review

Scope: explicit one-prompt preview only. No paid calls or live sweep were used to
validate this milestone. OpenAI Docs guided the matching token-count payload and
the output-cap/usage treatment; executable behavior is tested against fixtures.

| Attack or failure | Implemented control | Residual risk |
| --- | --- | --- |
| Generation begins before admission | Count, bound and file-fsync reservation before response call | Counting already transfers input; counting charges are outside this control |
| Understated or stale rates | Explicit model-specific, time-bounded operator policy | Rates/provenance are not independently authenticated |
| Cache/reasoning accounting understates spend | Uncached input rate; total output counted once; upward integer rounding | Assumes chosen rates cover applicable pricing thresholds |
| Additional billable capabilities | Text-only allowlist, no tools/references, fixed standard tier | Provider contracts still need credentialed conformance |
| Timeout triggers duplicate charge | Single-use controller and SDK retries disabled; retain reservation | A new invocation can spend again; no aggregate ledger |
| Concurrent calls share a reservation | Single-use flag set before first await | Separate controllers/processes have independent budgets |
| Unexpected usage/model/tier silently settles | Fail closed; violation/uncertain receipt; no complete manifest | Detection cannot undo charges or bound a provider contract violation |
| Existing reservation is overwritten | Exclusive private file creation; failure prevents generation | Trusted local filesystem; not a power-loss transactional ledger |
| Changed receipt is accepted after rehashing | Cross-check receipt/policy/reservation/result | Coordinated artifact rewriting is not prevented by unsigned hashes |
| Environment redirects credentialed requests | Fixed API base, no environment proxies or redirects | Same-UID host processes remain trusted |
| Budget tests spend real credits | Fake transports and SDK mocks only | No evidence of live capability or pricing conformance yet |

Next milestone: container-isolated live evaluation plus an aggregate spending
ledger, followed by explicit credentialed conformance. Automatic difficulty routing
remains disabled until held-out empirical gates pass. Local spending controls do
not close the label-isolation or independent-grader trust gaps.
