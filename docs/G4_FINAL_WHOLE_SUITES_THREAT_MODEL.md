# G4 final whole-suite threat model

## Scope and ownership

- System: separately signed final creator/reviewer whole-suite execution, schema 1.
- Owner: Joshua Myers; implementation and self-verification by Codex.
- Trigger: new G4 final execution boundary, 2026-09-24.
- Out of scope: live provider child, final independent approval, release or merge.

## Assets, actors and boundaries

| Asset | Need | Boundary |
|---|---|---|
| Protected creator tests and frozen reviewer package | Exact bytes, complete collection | Creator/reviewer custody to trusted host and immutable worker |
| Final code and Git lineage | No stale or substituted tree | Trusted read-only Git and no-follow host snapshot |
| One-use signed approval and result | No duplicate or forged positive result | Enrolled creator signature, private claim store and receipt replay |

The host, same-UID storage, enrolled key custody, Git binary/object store, Docker
daemon/image/kernel and clock are trusted. Test code is untrusted and runs only in
the existing no-mount, network-disabled worker. A model response or test file may
not grant authority.

## Abuse cases and controls

| Abuse case | Control and evidence | Residual risk |
|---|---|---|
| Changed, omitted or disguised creator tests | Exact signed test inventory, test-pattern/fixture classification, base/final Git and checkout byte equality, frozen-package verification | Approval's earlier creator-suite digest was opaque; final signature binds both identities |
| Reviewer tests bypass adapter or collection | Existing binding/worker validation, exact counts and candidate/final test-ID equality | Dynamic Python semantics are not a proof of test quality |
| Stale code, wrong image, replay or concurrent run | Candidate/provenance replay, request/image hashes, exclusive persistent claim, post-run replay | Same-UID store control and local clock remain trusted |
| Partial run or forged passing flag | No receipt on infrastructure failure; separate observations and model validation; replay against current inputs | Host/container observation authenticity is not independently attested |
| Source exfiltration or privileged test behavior | No mounts, network, credentials or provider route; bounded resources and output | Docker daemon, image and kernel remain trusted |

## Decisions

- A failing suite is retained as non-accepting evidence; it is never auto-retried.
- Approval authorizes tests only, not independent review or implementation acceptance.
- Required evidence: focused positive/negative/CLI tests, static checks, full gate,
  installed-wheel smoke and accountable review before any production exercise.
