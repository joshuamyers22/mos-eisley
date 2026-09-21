# Threat Model: structured review output and quorum resilience

## Scope and ownership

- System/version: Mos Eisley review model bridge through `57fe5cd` plus this change
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
| Standalone replay bundle | private integrity evidence | complete authentication inputs, bounded private exclusive retention | Joshua Myers |

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
| Tolerated critic error is misclassified after judge success | observation requires every critic rather than policy quorum | complete review cannot retain authenticated evidence | reconstruct the finished controller and reject infrastructure verdicts while preserving critic error records | full-path one-invalid-of-three observation authentication | the failed role remains visible and settled |
| Standalone host loses replay inputs with its ephemeral key | policies or phase signatures remain process-local | signed observation cannot be historically authenticated | verify and exclusively retain one bounded bundle before host exit | disk-only decode/authentication and tamper tests | trusted same-user storage remains required |
| Retained response limit is omitted during reconstruction | replay uses a default different from the live launch | post-result evidence fails despite an otherwise valid run, or a substituted projection is trusted | construct every dispatch-refusing reviewer with the retained launch limit and compare exact critic/judge projections | changed-limit campaign regression and full-path standalone test | future request-shaping fields require the same explicit binding |
| Malformed object schema bypasses strict normalization | object has absent or non-object `properties` | misleading strict claim or provider rejection | normalize missing properties to an empty object and reject malformed types recursively | direct schema fault tests | provider-supported JSON Schema subset can still evolve |

## Decisions

- Accepted risks with owner and expiry: provider-native schema reduces structural
  errors but does not guarantee substantive findings; Joshua Myers owns the decision
  to authorize any live retest and its same-provider correlation risk.
- Required tests and monitoring: exact schema projection, capability fallback,
  duplicate rejection, schema compatibility, one-invalid-of-three quorum through
  signed observation authentication, and complete retained-bundle replay.
- Incident and recovery dependencies: fail closed without retry; retained evidence,
  spend settlement, container cleanup, and fresh authorization remain authoritative.
