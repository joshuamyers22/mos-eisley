# Milestone 45 adversarial review: conformance ceremony preflight

## Disposition

Accepted as a no-send, pre-credential commitment for one exact paid-capable OpenAI
conformance attempt. Rejected as a spend reservation, data-transfer authorization,
provider receipt, observer signature, successful conformance result, or scoring input.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A policy is created after seeing the provider result | Add a dedicated preparation command that needs no credential and fixes the provider request before dispatch | External creation time and custody are not notarized |
| A nearby sample, model, effort, prompt, or output ceiling is sent | Reconstruct and hash the exact assignment-derived strict request at preparation and immediately before credential access | Trusted local code and source files remain in the trust base |
| A different spending scope or audit is substituted | Pin spend-policy, ledger, and audit-derived ledger-entry identities; require the entry and audit path to be fresh | Same-UID path races and ledger rollback/cloning remain possible |
| The policy outlives financial authority | Require the ceremony window to fit wholly inside the spend-policy window and require both to be current | Host clock correctness remains trusted |
| An unreviewed SDK serialization crosses the boundary | Pin sorted allowed versions and compare the installed `openai` distribution before credential access | Package provenance and SDK behavior are not independently attested |
| A policy expires during an allowed request | Require the remaining policy window to cover the configured request timeout | Scheduling and host-clock manipulation remain trusted |
| Preparation is mistaken for a reservation or live request | Do not access `OPENAI_API_KEY`, create the audit, reserve the ledger, start Docker, or dispatch; emit explicit false event flags | A separately authorized later command is paid-capable |
| A stale entry or blocked ledger defers failure until after credential access | Check blocked state and the exact unused entry during both preparation and live preflight | Concurrent ledger state can change; atomic spending admission remains authoritative |
| A successful probe is silently promoted into evidence | Preserve literal denial of conversion, grading, scoring, promotion, and activation | The separate signed conformance receipt is still required after a real success |

## Verification scope

Tests cover exact policy construction, no audit or reservation side effect, current
matching preflight, SDK/time/audit substitution, spend-window extension, reused ledger
identity, CLI no-credential/no-dispatch behavior, overlap rejection, and the existing
successful and failed broker lifecycle. All provider and Docker behavior remains
synthetic; no credentialed or paid request is made.
