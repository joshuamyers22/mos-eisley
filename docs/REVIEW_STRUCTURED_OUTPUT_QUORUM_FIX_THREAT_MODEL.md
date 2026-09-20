# Threat Model: structured review output and quorum resilience

## Scope and ownership

- System/version: Mos Eisley review model bridge at `6213cce` plus this change
- Owner and reviewers: Joshua Myers
- Date and review trigger: 2026-09-20; revisit on response-schema or provider change
- In scope / out of scope: canonical response-format contract, OpenAI projection,
  reviewer schema selection, and redundant quorum behavior / live dispatch,
  credential handling, provider quality, and launch qualification are out of scope

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Review request and schema | private source/review data | exact request binding and bounded size | Joshua Myers |
| Critic/judge response | untrusted provider output | strict validation before quorum/verdict | Joshua Myers |
| Spend and dispatch authority | financial/privileged | never implied by schema or offline tests | Joshua Myers |

- Actors and capabilities: local operator; untrusted model/provider response; broker
  and spending controls; malicious review content embedded as data.
- Entry points and trust boundaries: canonical `ModelRequest` to provider adapter;
  provider JSON back to the strict local decoder; critic results into quorum policy.
- Data flows and external dependencies: an authorized future run may send the schema
  and already-approved review data to OpenAI; this implementation performs no send.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Schema field grants dispatch or spend | caller has request construction access | unauthorized paid call | authority remains in broker/spend layers; format is declarative only | boundary tests/docs | caller can still seek separate authority |
| Provider emits duplicates or malformed nested values | adversarial or drifting model | false evidence or quorum confusion | retain duplicate-aware local JSON parsing and typed validation | negative regressions | provider may fail closed |
| Optional fields make OpenAI schema non-strict | Pydantic defaults/nullable fields | provider rejection or omission | recursively remove defaults/titles, require all properties, forbid extras | recursive schema test | provider may change supported schema subset |
| Schema is sent to an incapable model | incorrect capability routing | request failure | attach only when `ModelSpec.structured_output` is true | capable/incapable tests | registry metadata can become stale |
| Redundant critics amplify cost/data transfer | three-critic live plan approved | higher spend and exposure | exact preauthorization, independent reservations, no retry, bounded roster | controller and launch gates | one additional critic cost per run |
| One malicious critic controls outcome | threshold reduced or outputs conflated | incorrect judge input | keep threshold two and existing evidence validation/deduplication | three-critic fault test | same-provider failures may correlate |

## Decisions

- Accepted risks with owner and expiry: provider-native schema reduces structural
  errors but does not guarantee substantive findings; Joshua Myers owns the decision
  to authorize any live retest and its same-provider correlation risk.
- Required tests and monitoring: exact schema projection, capability fallback,
  duplicate rejection, schema compatibility, and one-invalid-of-three quorum.
- Incident and recovery dependencies: fail closed without retry; retained evidence,
  spend settlement, container cleanup, and fresh authorization remain authoritative.
