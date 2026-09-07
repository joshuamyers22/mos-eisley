# Milestone 50 adversarial review: synthetic Responses canary

## Disposition

Accepted for implementation as a narrow, independently authorized capability probe.
No live generation was used to validate this milestone; automated tests use synthetic
transports. A fresh operator-signed live run remains required.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Metadata visibility is treated as generation access | Distinct fixed Responses canary and result schema | One success does not predict future availability |
| A canary becomes an arbitrary prompt exfiltration command | No prompt/model/effort/tool overrides; only fixed repository-owned synthetic text | A modified release can change the fixed text |
| Local confirmation alone authorizes paid transfer | Require a separately enrolled Ed25519 signature plus explicit local acknowledgement | Signer independence and informed review remain procedural |
| A signer approves an opaque hash without seeing transferred text | Embed the full fixed synthetic request alongside both request hashes in the signed authorization | Signer must still review controls and key custody externally |
| A valid signature is replayed against another request, ledger, or path | Bind both request hashes, spend policy, ledger and path-derived one-use entry | Filesystem or ledger rollback/cloning remains possible |
| The token-count preflight is an unacknowledged extra request | Authorize and bind exactly one count plus one generation request | A remote service may internally process accepted requests differently |
| Cost exceeds the authority's expectation | Bind worst-case cost from policy input ceiling plus fixed 32-token output; require available coverage before key access and reserve atomically before generation | Local ledger is not an account-wide or invoice cap |
| Authorization expires between preflight and dispatch | Bind timeout, require window coverage, and reverify immediately before dispatch | Host clock correctness remains trusted |
| A caller restores compression, redirects, streaming, or retries | Reuse final-boundary identity encoding, redirect denial, bounded decoding, foreground mode, and SDK retries zero | Trusted SDK/HTTP implementation remains in scope |
| A response uses a different model, tier, usage, or tool | Fail closed before a final manifest; retain conservative spend evidence | Invalid but billable provider output can leave only partial evidence |
| A partial run is mistaken for verified access | Write the content-addressed manifest last and provide offline ledger-backed verification | External retention is needed to detect deletion or rollback |
| Canary success enables evaluation or routing | Result keeps billing, grading, scoring, promotion, and routing authority literally false | Consumers must continue to reject schema substitution |

## Verification status

Tests cover signature and expiry failures, path/timeout/ledger substitution, exact
request shapes, absence of user content in authorization, dispatch-time preserved-
input checks, shared-ledger settlement, uncertain failure retention, content-addressed
replay, tamper rejection, credential exclusion, and pre-credential CLI ordering.
