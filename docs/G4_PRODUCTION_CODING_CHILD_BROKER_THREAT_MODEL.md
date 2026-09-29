# G4 production coding-child broker threat model

## Scope and ownership

- System/version: G4 one-call production coding-child broker, schema 1.
- Owner/review trigger: Joshua Myers; new provider, credential, signing and spending boundary.
- In scope: exact authorization, transfer, isolated request, local accounting,
  child signing, replay. Out of scope: upstream invoice, hostile host, final acceptance.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Frozen offer and creator tests | Private source/test data | Exact approved bytes, no extra paths | Creator |
| Creator and child signing keys | Secret capability | Enrolled distinct roles, never sent to model | Key custodians |
| OpenAI credential | Secret capability | Trusted host transport only | Operator |
| Spend ledger and run records | Financial/audit | Durable one-use reserve, conservative failure | Operator |

The model may control only its response text. The worker has no network, mounts,
secrets or write authority. The trusted host composes the official provider
transport and consumes the broker claim. Signed creator approval, private ledger
and dispatch claim are independent authority boundaries.

## Abuse cases and controls

| Abuse case | Impact | Control and evidence | Residual risk |
|---|---|---|---|
| Reuse or mutate a grant/offer | Duplicate spend or broader source disclosure | Domain signature, exact offer/request hashes, digest-derived ledger ID and duplicate negative test | Same-UID host can tamper with local state |
| Prompt injection or tool request | Exfiltration or expanded authority | No provider tools, stateless request, bounded output, parsed replacement scope, isolated validation | Source/test bytes leave machine after separate approval |
| Malformed/refused/oversize answer | Fabricated code or crash | Strict JSON, completed-text check, byte cap, immutable child signature only after validation | Paid invalid answer still settles |
| Token-count, price or model mismatch | Unbounded or misreported cost | Full conservative reservation, current schema-2 pricing, counted input, provider usage/model/tier checks, ledger block on violation | Provider usage is not an independent invoice |
| Timeout, cancellation or network failure | Duplicate send or erased exposure | One-use claim and ledger ID, no retry, uncertain hold, bounded worker cleanup | Manual recovery may be required |
| Key/transport or dependency compromise | False approval, credential loss | Enrolled distinct child key, injected trusted transport, immutable image and local audit | Physical key custody and upstream service are trusted |

## Decisions

- Accepted risk: same-UID host, clock, Docker and credential custody remain trusted;
  owner must review before live use. No approval to make a live call is inferred.
- Required tests: exact and duplicate authorization, settled/invalid response,
  ledger/audit replay, source scope, uncertain-send path, existing broker timeout
  regressions, clean build and whole suite.
- Incident/recovery: retain private run directory and ledger hold; inspect before
  deciding whether upstream billing occurred. Do not auto-release or retry.
