# Threat Model: content-bound review citations

## Scope and ownership

- System/version: Mos Eisley review critic request schema 2
- Owner and reviewers: Joshua Myers
- Date and review trigger: 2026-09-20; citation-fidelity failure in the final live test
- In scope / out of scope: offline citation projection and validation are in scope;
  model quality, live dispatch, credentials, spending and sealed-run mutation are out.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Frozen review brief | owner-selected source | exact bytes and identity | Joshua Myers |
| Critic evidence | untrusted model output | exact source binding | review pipeline |
| Historical schema-1 artifacts | private retained evidence | immutable and replayable | Joshua Myers |

- Actors and capabilities: an untrusted critic can invent fields, unit IDs and quotes;
  an operator can supply arbitrary bounded diff text.
- Entry points and trust boundaries: `CriticRequest` construction, model JSON reply,
  offline evidence reconstruction and judge admission.
- Data flows and external dependencies: deterministic local parsing only; no new
  dependency or external service.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Invented or stale unit ID | malicious/errant critic | unsupported finding admitted | recompute exact catalog from frozen diff and require an exact ID | adversarial tests | SHA-256 collision is accepted as negligible |
| Cross-hunk line splicing | related text in separate hunks | fabricated multiline claim | each derived quote resolves within one unit only | cross-hunk test | raw unit can cite real intervening patch syntax |
| Whitespace normalization | visually similar code | source meaning drifts | exact substring comparison with no normalization | whitespace test | model must quote exact source text |
| Catalog amplification | many synthetic hunk headers | request-size denial of service | bounded diff and maximum hunk/unit count | boundary test | large valid catalogs consume budget and fail closed |
| Historical reinterpretation | code upgrade during replay | sealed result changes | schema-1 preserves old prompt, bytes and validation | compatibility test | schema 1 retains its known expressiveness limit |
| Prompt injection in diff | adversarial source text | model follows review data as instructions | existing data-boundary prompt plus deterministic validation | reviewer tests | model quality remains advisory |

## Decisions

- Accepted risks with owner and expiry: schema 1 keeps raw-only validation indefinitely
  for exact historical replay; new production preparation must use schema 2.
- Required tests and monitoring: unit derivation, binding failures, request-size bounds,
  retained-shape regression, schema-1 prompt isolation, full offline and container
  gates. All passed on 2026-09-20.
- Incident and recovery dependencies: roll back schema-2 launch preparation; never
  edit or reuse a sealed live campaign.
