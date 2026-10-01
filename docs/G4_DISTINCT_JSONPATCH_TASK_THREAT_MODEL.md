# Threat model: distinct bounded JSON Patch G4 task

## Scope and ownership

- System/version: one isolated G4 JSON Patch initial child and possible correction
- Owner: Joshua Myers in disclosed single-operator creator/reviewer/VCS mode
- Date and trigger: 2026-09-28, fresh task after passing CSV candidate
- Scope: private task package, frozen tests, isolated child proposal and later gated correction

## Assets, actors and boundaries

| Asset | Integrity need | Owner |
|---|---|---|
| Plan, protected tests and blind reviewer package | Fixed before initial child | Joshua |
| Clean target commit and one owned source path | Exact Git/proposal lineage | Joshua and VCS gate |
| Owner key and fresh child key | Domain-separated signatures | Joshua; private task root |
| Shared spend ledger | One-use exact holds and settlement | Spend controller |

The child can propose only `src/json_patch_lab/patch.py`; it has no authority
to edit tests, approve its work, access credentials, or call a provider without
a separate signed grant. Blind reviewer bytes stay outside the child Git tree.
Known-good and known-bad fixtures are isolated controls, not candidate results.

## Abuse cases and controls

| Abuse case | Impact | Control and evidence | Residual risk |
|---|---|---|---|
| Changed tests after approval | False pass/fail | Exact hashes, frozen package, replay and clean Git base | Oracle can be incomplete |
| Fabricated correction trigger | False end-to-end qualification | Two separately signed matching failed candidates and signed triage | Same human controls roles |
| Proposal writes outside owned path | Unauthorized code change | Signed assignment, diff ownership and isolated integration | Static checks have semantic limits |
| Replayed or substituted provider call | Unbounded spend or wrong source | Exact one-use grant, frozen offer, private claim and settled ledger | External provider behavior varies |
| Malformed or cyclic JSON tree | Resource failure or mutation | Bounded plan, protected/reviewer tests and contained worker | Untested edge cases remain possible |
| Source or package change during tests | Misbound evidence | Immutable binding and post-run source verification | Host/worker assumptions remain |

## Decisions

The task stops if its first genuine candidate passes, a control fails, source
or tests change after approval, a receipt is incomplete, the ledger is
unresolved, or a required signature is absent. No correction is inferred from
the known-bad fixture. A later final decision must disclose single-operator
risk and separately satisfy review, quality applicability and acceptance.
