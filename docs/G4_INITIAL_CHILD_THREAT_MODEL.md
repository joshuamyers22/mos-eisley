# G4 initial-child threat model

## Scope and ownership

Joshua Myers owns the one-human G4 qualification. The new initial-child route
starts at a fresh assignment over the already approved task and ends at a
child-signed, scope-checked proposal with measured provider spend. Git integration,
candidate tests, final suites and review are downstream boundaries.

| Asset | Owner | Need |
|---|---|---|
| Approved plan, creator tests and base Git source | Joshua | Exact bytes and revision before dispatch |
| Blind reviewer package | Joshua as reviewer custodian | No child disclosure or mutation |
| Creator and child signing keys | Local operator / trusted host | Never enter model or repository |
| Shared spend ledger and private audit | Joshua | Atomic one-use reserve and fail-closed settlement |
| Provider proposal | Untrusted model | Bounded parse, path and byte validation |

## Abuse cases and controls

| Abuse case | Control | Evidence to require |
|---|---|---|
| Reuse of seeded or correction receipt as an initial child | New artifact kind, domain, task and assignment links | Wrong-kind and wrong-hash rejection |
| Stale plan, tests, source or assignment | Exact signed chain and Git re-read at dispatch | Mutation negative tests |
| Model reads hidden reviewer tests or keys | Explicit offer only, no tools or mounts; host owns transport/key | Request and worker inspection |
| Model changes tests, new paths or unchanged files | Existing-path allowlist and canonical replacement validation | Scope negative tests |
| Replay of a live grant or crash after reservation | Ledger entry keyed by signed grant; private claim and audit | Duplicate and failure fixtures |
| Unbounded spend or uncertain upstream send | Conservative reservation and retained hold | Usage, timeout and failure fixtures |
| Forged child provenance | Host signs only validated response with enrolled child key | Foreign-key and tamper fixtures |

The same-UID host, local clock, Git executable, Docker image/daemon, signing-key
custody and provider usage report remain trusted. A signature authenticates a
key, not a person's independent judgment. No live authority follows from an
offline test or this document.
