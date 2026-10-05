# G4 negative-case gap resolution

Prepared 2026-10-01. Base controller:
`6ec5f46e4150edc55457e5296269db66b1047097`; changes remain in the worktree.
Objective: resolve concrete applicable enforcement gaps using existing accepted
task evidence and synthetic attacks, retaining unsupported claims as blockers.
Formal independent review remains on hold.

Guidance: [Python guide](PYTHON_ENGINEERING_GUIDE.md),
[verification guide](AGENTIC_VERIFICATION_GUIDE.md),
[work-note template](../templates/WORK_NOTE.md),
[verification loop](../templates/AGENTIC_VERIFICATION_LOOP.md) and
[threat-model template](../templates/THREAT_MODEL.md).
Risk: test acceptance, spending and authorization boundaries. Resource limit:
focused offline regressions, four bounded Docker probes and disposable storage
audits; no provider calls, cloud writes, accepted-task execution or study access.

## Changes and observations

| Case | Observation / action | Result and limit |
|---|---|---|
| B1 | Added fixture-data mutation with unchanged assertion bytes, complementing the existing oracle mutation check. | Rejected; freeze inventory remains exact. |
| B3 | Declared expected-failure runtime fixture incorrectly qualified as passing. | Fixed both receipt creation and replay validation to require zero expected failures for known-good, candidate and known-bad roles. Forged passing receipts are rejected. |
| B5/C4 | Added nonmatching reproduction, error, unexpected success, execution-inventory mismatch and incomplete two-failure triage scenarios. | Denied before any correction claim. Matching two runs is not proof that a test is never flaky. |
| C1/C2/C3/C5 | Present but irrelevant quote and wrong-oracle premise; signed test-defect, plan-gap, flaky, infrastructure and unresolved triage paired with an enrolled creator's matching approval. | Creator acquiescence cannot override nonimplementation triage. Semantic diagnosis remains the judge's responsibility. |
| C6/C7 | Added carried-use reset and enlarged-ceiling attempts against persisted prior completion. | Rejected; exhausted/failed cycles still grant no acceptance. |
| S1 | Withdrew the exact pre-reserved hold during token count. | Generation denied, full exposure retained, no retry. Protected remote stage admission adds a prospective external revocation boundary. |
| B6 | Actual immutable-image probes for process count, memory, output and deadline limits. | All four passed, all four containers removed. No host mounts or network access. |
| S2/S5 | Copied a synthetic pre-spend ledger and restored the original path to its pre-spend bytes. | Both could reaccept the same entry. This is failed anti-rollback evidence, not a passing duplicate check. |
| S1/S2/S4/S5 | Joshua required protected remote storage; Codex selected DynamoDB behind an admission service. Added separately signed protected-anchor binding, fresh signed stage responses and fail-closed G4 broker integration. | Synthetic client/service boundary passes; deployed storage, IAM and service qualification remain open. No local fallback. |

The receipt fix changes interpretation of an old expected-failure-containing
passing receipt: it no longer qualifies. This is intentional. D/T's accepted
final suites contained no expected failures; their private artifacts, signatures
and accepted scope are unchanged. They do not acquire new protected-storage
evidence retrospectively.

## Trust and abuse boundaries

Assets: exact task authority, cumulative spending, spent grant identities,
frozen tests and retained evidence. The model and worker are untrusted; enrolled
review judgments remain accountable semantic attestations. Local task storage
can be copied/restored. The new remote service must enforce owner isolation,
one-use stages and current aggregate state outside that restore authority.

| Abuse | Control / remaining risk |
|---|---|
| Hide failures with xfail or empty/skip collection | Runtime and replay checks deny qualification; collection counts remain visible. |
| Approve a wrong oracle or new invariant as coding correction | Nonimplementation dispositions deny despite creator signature. Hash/signature checks do not automatically establish semantic relevance. |
| Reset carried task/review spend or replay a local ledger | Persisted cycle checks plus prospective remote aggregate admission. Remote deployment evidence remains mandatory. |
| Substitute another owner, epoch, request or stale remote response | Owner-signed exact binding, service enrollment contract, nonce-bound service signatures and increasing sequence; real IAM enrollment still needs qualification. |
| Remote outage or uncertain admission | Spend attempt before the external call, retain exposure and stop without fallback/retry. |

No remote-admin compromise guarantee is claimed. The task operator must have no
permission to rewrite/restore the protected state, signer or service policy.
See the [anchor design](G4_PROTECTED_STORAGE_ANCHOR_DESIGN.md) for the selected
deployment and required fault receipts.

## Verification record

- Before the protected-anchor additions: all 153 reviewer regression tests passed
  in one batch (332.957 seconds), including the receipt fix and correction
  denial/reset scenarios. The later explicit irrelevant-quote premise passed its
  focused correction-bridge rerun. This result does not include the later anchor code.
- After anchor integration: 13 correction-broker tests, four initial-broker tests
  and nine protected-anchor tests passed. The anchor fixtures perform no network
  or cloud operations.
- The spending suite passed all 23 tests, including withdrawal during count.
- Repository-wide Ruff lint, formatting and Pyright checks passed. Pyright used
  the project virtualenv explicitly; an initial invocation without that interpreter
  reported missing dependencies and was not counted as passing. No uninterrupted full `make check` or publication
  qualification is claimed.

Actual container image:
`sha256:082d662d52e38e23a0d91a4aae54cd30be08f60d3deaf76a133507bb8be82a79`.
The image supplied the worker Python environment; the host used the selected
worktree's `OfflineContainer` controller. This is containment evidence, not a
claim that every current application module is installed in that image.

Private container receipt: `/private/tmp/g4-negative-containment-2026-10-01.json`.
SHA-256: `3ad0baa318645aa6e495fff96261cabbed3f55b768da566e1d573cfa3f38a806`.
It retains scenario digests and cleanup records. Its tool digest identifies the
pre-format tool bytes used for that run; subsequent formatting does not turn it
into a new run. Controller digest:
`d18de9a40813629429dcf9afd074f82603714ab68b304ac77665ecd8aea24730`.

Private failed storage-audit receipt:
`/private/tmp/g4-storage-limit-audit-2026-10-01.json`.
SHA-256: `21d201cffff5e655cce6a0e70b7e5cb0ba363a3afff0d4cae80794386cb00ee8`.
It concerns only disposable synthetic databases. Original signed task ledgers
were not opened for writes or reset.

## Handoff

The [inventory](G4_NEGATIVE_CASE_INVENTORY.md) identifies verified enforcement,
adjudication-dependent semantic checks and the remote qualification blocker.
Live G4 coding now refuses to proceed without the new protected binding/service.
No usable production anchor is configured or deployed by this work.

Next: supply the actual AWS deployment identity and qualify its service/IAM
boundary, then obtain fresh prospective owner binding and controller verification.
Broader semantic/review applicability decisions remain separate; independent
review stays on hold. No sampling registries, mappings, labels or outcome stores
were accessed, and no study eligibility or milestone acceptance is claimed.
