# Threat Model: sealed formal cleanup and conservative accounting

> **Post-campaign reassessment, 2026-09-23:** the binding is an inherited frozen,
> scalar contract and the independently pinned seal digest is the campaign identity.
> Existing post-start seal-tamper tests reach terminal cleanup. Direct tests now cover
> the terminal start-window lower and upper boundaries; see
> [the binding-claims reassessment](REVIEW_CLEANUP_BINDING_CLAIMS_REASSESSMENT.md).

## Scope and ownership

- System/version: brokered review controller after `98869cc`.
- Owner and reviewer: Joshua Myers.
- Date and trigger: 2026-09-23; two upheld formal-campaign findings.
- In scope: campaign binding, controller terminal cleanup, unused allowance
  retirement, transfer/uncertain state and offline inspection.
- Out of scope: provider behavior, retry, historical evidence mutation, arbitrary
  trusted-process code execution and live-review activation.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Sealed campaign slot | execution authority | Exact seal, slot, preview, ledger and policy must agree | Joshua Myers |
| Deferred judge allowance | financial integrity | Release only an exact unused held source | Joshua Myers |
| Transferred judge destination | financial integrity | Never release or obscure attempted-request exposure | Joshua Myers |
| Critic and unrelated entries | financial integrity | Cleanup must not mutate them | Joshua Myers |
| Terminal evidence | audit integrity | Marker must report only cleanup performed by this controller | Joshua Myers |

- Actors: callers using supported library APIs, the trusted host composition root,
  local artifact tampering and provider failures represented by uncertain receipts.
- Entry points: controller construction, sealed probe construction, terminal cleanup,
  ledger retirement and stopped-run inspection.
- Data flow: a sealed binding selects one committed preview and ledger; the controller
  retains that binding, revalidates it at cleanup, and supplies only its exact judge
  source entry to the ledger.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Direct formal controller retires without campaign admission | Formal envelope only | Capacity released outside committed campaign | Missing binding disables retirement | Direct-construction regression | Trusted code can call ledger primitives directly |
| Wrong seal, slot, preview or ledger is supplied | Substituted binding | Cleanup attributed to another campaign | Independent seal read and exact slot/preview/path/policy comparison | Campaign substitution tests | Local storage denial leaves conservative holds |
| Seal changes after construction | Artifact tampering | Stale admission used at terminal | Reread binding before cleanup; invalid binding performs no retirement | Terminal tamper regression | Terminal can record non-retirement only |
| Cleanup follows atomic judge transfer | Source settled at zero, destination exists | Destination exposure accidentally released | Exact source identity; non-held source is no-op | Transfer and repeated-cleanup regressions | Lost transfer artifacts can still make inspection incomplete |
| Cleanup follows uncertain receipt | Exact entry is uncertain | Conservative exposure understated | Exact non-held state is preserved unchanged | Uncertain-state regression | Manual reconciliation remains separate |
| Cleanup touches critics or unrelated entries | Shared ledger | Other exposure changes | Single-entry transaction plus before/after state assertions | Isolation regressions | Privileged direct SQL is outside the boundary |

## Decisions

- Preparation scope continues to control schema and judge timing, but no longer grants
  cleanup authority by itself.
- Only a validated immutable `ReviewCampaignBinding` enables formal cleanup, and the
  exact seal/slot/preview/ledger binding is rechecked at terminal time.
- An exact non-held allowance is a cleanup no-op; missing or mismatched identity still
  fails closed.
- Required verification: direct unbound formal cancellation, sealed cancellation,
  transfer, uncertain receipt, repeated cleanup, unrelated-entry isolation,
  post-start seal tampering, terminal start-window lower/upper boundaries,
  inspection, campaign dispatch, launch compatibility and the full repository gate.
