# rc.16 owner review, signing and affected qualification

Initial status: **blocked at RC16-Q02**. The subsequent
[diagnosis and final qualification](RC16_STARTUP_QUALIFICATION_REVIEW.md) passes
the reviewed profile; original failure and initial work below remain preserved. Owner: Joshua Myers; operator: Codex.
Started 2026-11-05 UTC; continuation 2026-11-06. Review before a new qualification
attempt or publication. [Technical disposition and bindings](RC16_QUALIFICATION_REVIEW.md).
Frozen runtime remains `14eb79d52950f340aba159815222e04e6ea864e3`, version
`0.1.0-rc.16`, storage epoch 2; published preview remains rc.15.

## Authority, invariants and selected guidance

The owner requested review/merge #366 then #367, protected signing and affected
rc.16 qualification. Selected guidance: AGENTS, publisher preparation/handoff,
Python engineering, agentic verification/adversarial guides, threat-model,
verification-loop and work-note templates, pinned by the production-template
survey. This is an owner-directed operator review, not independent human
attestation or general stable approval.

Block on wrong source/tag/signature/artifact, failed required assertions or
cleanup, or exhausted resource budget. Preserve all historical sources, campaign
roots, grants, ledgers and dated assessments. Never read private signing custody,
provider credentials or evaluation stores. Zero provider calls; no new grants,
draft release or publication. Supplementary controllers have separate identities
and cannot change frozen software. Ordinary release receipts convey no evaluation
eligibility.

## Completed work and gates

- #366 merged normally as `3344c8f5bfafe0804d5d4dd55314b853f3541a1f` after 14
  exact-head checks. #367 retargeted to main and merged normally as
  `b3a239a5b1bb9ec8efd8898dfd9e5201adda0dbf` after 18; its tree equals the
  frozen source retained in main history.
- Source `make check` passed 3,960 tests (17 skips), 86% coverage and 2,919 wheel
  tests (13 skips), captured exit 0, all 876 frozen inputs unchanged.
- Exactly one annotated tag, object `cdcb8240b84de4d909d345e35a08654064763535`,
  started protected run 42102119299, attempt 1. GitHub records the owner's signing
  approval; the operator submitted no duplicate approval or signing attempt.
- Protected preparation passed full check/audit, build/container and enrolled
  signing. Software SBOM has 6,496 components/6,497 dependency records; separate
  offline schema, marker/reader and five mutated-BOM rejection checks pass.
  All 418 runtime Python sources match in each signed archive.
- #368 merged normally as `93bf1bd2c99ae8aa66f27fcbb088a31d9162c36d`. Corrected
  supplementary harness `ca68fa9a4de83b70afa4877f392ec6b6994b86a1` passed seven
  offline tests, explicit type checks and a combined full gate: 3,960 source and
  2,919 wheel tests, 86% coverage, 879 unchanged inputs. Its dispatch-only native
  job was skipped during PR checks and was not credited as executed.

## Original resource failure and continuation

Initial window: six hours, one protected run/signing approval, zero workflow
retries. Three full original signed platform jobs passed. Intel job 127590446087
exceeded its 75-minute limit and ended cancelled at 2026-11-06 00:15:02Z; GitHub's
explicit execution-limit annotation is retained. Installation, both stores and
predecessors through rc.13 passed. rc.14 was interrupted; rc.15/progress/formula
were skipped. Publication was skipped; the original run remains cancelled.

The server interruption outlasted the original observation window. A separate
three-hour continuation was bounded to 14:20–17:20Z on 2026-11-06: one read-only
dispatch, four Intel groups at 40 minutes each and four dependent discovery jobs
at 20 minutes each, no signing or publication. Controller
`efba0d4781f0e5e4dd3c3cfa9e2b9efe31aa9d3c` in #369 preserves all 16 original
Intel assertion commands and fixed runtime source/version arguments. Strict
admission requires exact original run/attempt/source, successful preparation,
three passed platforms and the specific cancelled Intel job/timeout annotation.
Five admission challenges and seven existing discovery tests pass; explicit Ruff
and pyright pass. Normal exact-head CI remains distinct from installed results.

Read-only run 42233939365 dispatched once at 14:26:31Z. All three predecessor
groups passed. Group 0 failed staged native version verification with the unchanged
30-second deadline in the smoke test's synthetic interruption fixture (RC16-Q02).
No signed-install report was written; dependent installed/progress/formula and
public discovery were skipped. Actual publisher-bootstrap completion and earlier
Intel install/both-store reports do not override the fresh failure. No retry,
profile relaxation or replacement candidate was launched. Startup root cause
remains undetermined; next work needs bounded startup/loader diagnostics.

Reconstruction authenticates **60 partial reports**, including all 48 actual
predecessor journeys and four rc.7 refusals. Original partial Intel reports remain
separate from twelve fresh predecessor reports. Missing Intel progress/formula
and the fresh smoke failure block complete qualification. Software-only SBOM
review is successful; complete 62-report/80-asset publication admission and
publisher preflight are not claimed. Four-target real discovery remains unrun.

## Preserved earlier failures

Original source fixture/type errors and interrupted gates remain in preparation
records. A local tag preflight used host Python 3.9 without tomllib and failed
before tag creation; project Python corrected it, with exactly one tag pushed.
The signing-approval guard stopped because the owner had already approved; zero
operator approval POSTs were submitted.

Static review before supplementary native dispatch caught bootstrap text being
parsed as JSON. The seventh offline regression reproduced it; execution and JSON
decoding were separated. The invalidated first combined-gate input snapshot and
log remain retained, not passing evidence. A restricted local rc.15 preflight
failed without an exact retained native defect. Escalated native commands exited
0, then a controller expected the wrong policy-response field; offline analysis
corrected that expectation. No complete preflight pass is claimed. An early SBOM
publication audit correctly refused missing reports; the final audit is explicitly
software-only. ANSI log-download refusal was corrected without executing logs.

## Handoff

Owner-directed source review and requested merges/signing are complete. Installed
qualification remains blocked; no publication approval follows. The original
publisher is skipped, and read-only continuation cannot make it green. Any future
publication needs a reviewed protected path admitting complete exact-artifact
results and separate owner authorization. rc.15/readiness and rc.14 live evidence
retain their original scopes; no stable, WSL2, cask/tap publication or new native
subscription qualification is claimed.
