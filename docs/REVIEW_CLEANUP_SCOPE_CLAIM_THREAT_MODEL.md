# Threat Model: cleanup-scope construction invariant

## Scope and ownership

- System/version: brokered review controller at `24704aa6fc4aadba2dcec79b8f83bae44f01a02d`.
- Owner and reviewer: Joshua Myers; accountable disposition remains required.
- Date and trigger: 2026-09-23; one claim repeated by all critics and judges across a three-slot single-provider campaign.
- In scope: supported controller construction, formal/standard scope binding, terminal cleanup, live conformance and offline inspection. Out of scope: arbitrary trusted-process code execution, historical evidence rewriting, provider behavior, retry and launch activation.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Controller authorization and envelope | authorization metadata | Schema and preparation scope must remain equivalent | Joshua Myers |
| Deferred judge allowance | financial integrity | Retire only the exact unused formal source | Joshua Myers |
| Campaign binding | live authority | Formal live execution requires an exact retained seal | Joshua Myers |
| Terminal and inspection records | operational evidence | Standard artifacts cannot claim formal cleanup | Joshua Myers |

- Actors: untrusted model content, callers using supported public APIs, the trusted process-local composition root, and a privileged caller able to mutate Python-private state.
- Entry points: prepared calls/envelopes, controller constructor, live conformance probe, terminal transition and read-only inspection.
- Data flows: immutable preparation scope flows from critic authorizations to the judge allowance, envelope, derived controller authorization/start, terminal marker and inspector.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Inject schema 2 into a standard controller | Public authorization injection or setter | Standard allowance retirement | Constructor derives authorization; preview enforces schema/scope equivalence; property has no setter | Constructor trace, public-API probe, substitution regression | Python-private mutation remains trusted-process compromise |
| Mix standard critics with a formal judge allowance | Mutable or incoherent envelope | Scope confusion and wrong deadline | Frozen contracts; envelope validator requires every scope to match | `ReviewSpendingEnvelope.coherent_envelope` | Privileged object-forging is outside the boundary |
| Execute formal live preparation without a seal | Formal envelope passed to production probe without campaign | Extended authority outside campaign custody | Conformance probe records the unbound state and refuses `run` | `_extended_preparation_unbound` gate | Lower-level controller remains usable for offline/tests by design |
| Forge a standard cleanup marker after execution | Same-owner artifact tampering | False complete spending attribution | Inspector requires schema-2 start and exact formal envelope scope | Standard-marker rejection regression | Inspection cannot undo prior privileged ledger tampering |
| Same model repeats an unreachable counterexample | Correlated prompts and evidence | Unnecessary code churn or weakened architecture | Normalize claims; trace reachability; require executable counterexample | Three-slot campaign plus this reassessment | Single-provider review is not independent judgment |
| Add a redundant terminal scope check as a security claim | Misclassify representation invariant as untrusted input | False confidence without containment | Preserve trust-boundary statement; require a separate design if host containment changes | Source trace and adversarial review guide | A readability-only change may still be chosen separately |

## Decisions

- Reject the repeated schema-2/non-formal claim as unreachable through supported controller and production-live APIs.
- Do not change runtime code merely to make a correlated reviewer withdraw an unsupported finding.
- Retain the explicit residual that arbitrary trusted-process mutation is outside containment and that lower-level formal controllers exist for offline/tests; production live conformance remains seal-gated.
- Require human disposition before using this reassessment to advance G2 or authorizing another live campaign.
