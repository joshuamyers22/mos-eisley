# G6-06 R0–R6 offline technical review packet

Status: **offline technical review packet complete; independent acceptance and
live G6-06 gates open**, updated 2026-09-28. This packet assesses the synthetic chain in
the [G6-06 plan](G6_06_BOUNDED_ROLLOUT_ASSESSMENT_PLAN.md), its fixed
[full runner](../tools/g6_06_full_offline.py), phase validators and fault tests.
It is a source assessment and reproduction record, not an independent reviewer
decision, a target-host result, a G6-05 qualification, a cohort release or an
assessment of actual outcomes. G5 has qualified no policy and runtime preflight
still denies dispatch.

## Reviewed snapshot and local reproduction

The repository HEAD was `c6a427805a5eaf692de462c0f88ed42a4be5b8d0`.
The worktree was dirty; this review identifies the exact bytes by digest and
does not assert that HEAD alone reproduces them. The plan digest below includes
the source-binding update and its link to this packet. Documentation is outside
the runner's bound source set.

| Reviewed artifact | SHA-256 |
|---|---|
| [G6-06 plan](G6_06_BOUNDED_ROLLOUT_ASSESSMENT_PLAN.md) | `e726e08fa05633bf29c4876f2d57e4ecd25c08a3325384aef4c963e70bb36b54` |
| [G606-03 candidate freeze](G6_06_G60603_REPRODUCTION_FREEZE.md) | `7413ce0db0ceec4e2784fb75aa44be1f69735461f4985c905320a3c0660d6b1c` |
| [G6-06 blocker and re-entry packet](G6_06_BLOCKER_AND_REENTRY_PACKET.md) | `472c6c351a89107c217eab173ec84b420413b3f957067782b95792f51761d605` |
| [G606-04 operating-gate handoff](G6_06_G60604_OPERATING_GATE_HANDOFF.md) | `0a4ea084d846dd7d16a5cfb412abfa15fc31ff173f0e19e84b140311ff9451d0` |
| [G606-05 assessment source handoff](G6_06_G60605_ASSESSMENT_SOURCE_HANDOFF.md) | `e53eed95085bb4c70a431ff2d815f9f60e57f3a5347fa6b94b00babcf9f3939b` |
| [Full runner](../tools/g6_06_full_offline.py) | `0eaafe4f5d6783a436c9b092e86918b800c477fede37e51fddce0dc83d597315` |
| [R0 runner](../tools/g6_06_r0_offline.py) | `b86f3018f0d2e2e28d1e721870840fb67f8ac009ee79e234b26a170197c17978` |
| [Full-runner tests](../tests/test_g6_06_full_offline.py) | `78ea5b38c798ac13424d10299643675074f76ba4c10c30b0ae03c52f7ac18490` |
| [G606-02 handoff validator](../tools/g6_06_handoff_evidence.py) | `1adb0d021d714845f8626a70c854f0434b60595b79fbb7cb238b8c24a0851d6d` |
| [G606-02 synthetic tests](../tests/test_cohort_handoff_evidence.py) | `70604ce2dc3b0a7701ea69fc31a03b1bbd31d9e9501f115c55d019b58067fbb2` |
| [G606-03 reproduction validator](../tools/g6_06_reproduction_handoff.py) | `386b67b5951acc1722576ee3f126bea5dbc1fa00ccdf3836d7d472364774bf71` |
| [G606-03 synthetic tests](../tests/test_g6_06_reproduction_handoff.py) | `7d29e16a1cefecbe0924a544fb39bde4fdc0f085600582a6aecd59f30ca16875` |
| [G606-04 operating-gate validator](../tools/g6_06_operating_gate.py) | `4a564505da9118247ebc55020ea11905c327cfb2b628f29b6847b2e970c78996` |
| [G606-04 synthetic tests](../tests/test_g6_06_operating_gate.py) | `dca26b69c9216b291ffb3866f0c2ae614fb4906094afcf60c7af997adaa040ba` |
| [G606-05 source-coverage validator](../tools/g6_06_assessment_sources.py) | `a1fbbfffe22c24f2a8b21c4bca2ed25e539e8a1533a958fe679a9500b5e49d23` |
| [G606-05 synthetic tests](../tests/test_g6_06_assessment_sources.py) | `24f38c728a84e7b21e55bee344804fce9d363120232790fd2c64b060b52e0a25` |
| [R1 shadow source](../src/mos_eisley/run/cohort_shadow.py) | `529014602d27cb91d99e16ad57e6448a3f4cefe98a004c124b7793670b2cc130` (now source-bound; G606-01) |
| [R2 entry source](../src/mos_eisley/run/cohort_entry.py) | `f8b65ebacfd8a1f345dcf69dc163a56702c9327f9a90435b1b0ed2ad080f2f9d` |
| [R4 surveillance source](../src/mos_eisley/run/cohort_surveillance.py) | `34e1c148eeb7dd1391facb6f94de7e999d7ad9cb6978a946f6a29aa57d094b31` |
| [R5 close source](../src/mos_eisley/run/cohort_close_handoff.py) | `5944df5f90ede1f734fcac81fd23eb97c091c2e47bde3a6f538469483d0923ce` |
| [R6 assessment source](../src/mos_eisley/run/cohort_assessment_handoff.py) | `78c7eebbe92e1f9d83dae4634128ee3e80ea84fb96e06b0bc7ede57f59bfcb60` |

I ran `uv run --frozen python -m tools.g6_06_full_offline
/private/tmp/g6-06-g60605-sources-20260928.json` from the repository root. Its
mode-0600, metadata-only index has SHA-256
`24ee5c1840c30e0671ba4f72981a1dec6ac01bb864d07a8968f7ca7f964d8171`.
It reports `synthetic_pass`, `source_stable: true`, **314 of 314 tests**, 17
fixed suites, zero failures, errors or skips, and 306 bound source files.
The ordered source-set digest is
`07eb35d3b637be34449cdcf1e175fe6c10bdea582868967a7437711f0b937bad`.
The private index contains the per-file digests and per-suite case-ID digests;
it is an ephemeral local artifact, so an independent reviewer must rerun and
rehash the frozen candidate. The index's target-build, independent-review,
G6-05-qualified, cohort-release, dispatch and assessment fields are all
literal `false`.

The later [G606-03 local candidate package](G6_06_G60603_REPRODUCTION_FREEZE.md)
contains a fresh 314-case baseline index, the exact 306 bound source files, a
17-suite case-ID protocol and an independently checkable archive manifest. Its
fresh baseline raw SHA-256 is
`fd82d3aa07f5d3ccdb8b6665a4ed253c430c434f22bcace514599d167310621e`;
the canonical index digest used by the validator is
`9e04c7a549f217dbb229989c6cb912bb78642d85cf0663f5e9ed780ec3acf24a`.
The source-set digest is unchanged from the run above. A clean extraction by
the same preparer passed 314 cases with exactly matching source and suite
metadata. The package includes an invalid anchor-input template; external
build/host and reviewer claims, independent freeze and replay are still open.

The later [G606-04 candidate handoff](G6_06_G60604_OPERATING_GATE_HANDOFF.md)
pins all 35 C-fault names and code-owned oracles, supplies five deliberately
invalid input templates and 19 unreviewed O/C case slots, and records a
20-test synthetic preflight. No approved numeric ceiling, target-host
observation or independent decision was filled from the fixture.

The [G606-05 candidate handoff](G6_06_G60605_ASSESSMENT_SOURCE_HANDOFF.md)
fixes the nine descriptive and eleven comparative source kinds, carries three
deliberately invalid review/anchor templates and records a 23-test synthetic
preflight. Its eight upstream inputs are unset. No restricted source was
opened or represented as reviewed.

The [blocker and re-entry packet](G6_06_BLOCKER_AND_REENTRY_PACKET.md) binds a
later preparer-run rehash of all 306 bound sources and a fresh 314-case replay
with exact source/suite metadata match. The user reports only one available
human and no separate host. No independent anchor was frozen before that run,
so G606-01 and G606-03 remain open. Bounded-live entry is recorded as **hold
pending evidence** on the user's direction, without an authenticated owner/
operator signature or release decision.

| Fixed suite | Cases run | Scope |
|---|---:|---|
| G6-02 exact route | 10 | Resolver selection and denial |
| G6-03 one use | 22 | Local inert transaction and recovery |
| G6-04 witness/budget | 46 | Witnessed claim, controls and three scopes |
| G6-05 qualification | 71 | Promotion, activation and qualification metadata |
| G6-06 cohort | 63 | Controller, C04–C09, R0 integration and R0 runner tests |
| G6-05 host drills | 12 | Synthetic drill-index checks |
| G6-06 R1, R2, R3 | 6, 15, 9 | Shadow, entry and per-attempt handoffs |
| G6-06 R4, R5, R6 | 10, 8, 8 | Surveillance, close and assessment handoffs |
| G606-02 handoff evidence | 6 | Signed R0/R1/on-call and R5/R6 source joins and denials |
| G606-03 reproduction handoff | 6 | Frozen baseline and full digest/case comparison |
| G606-04 operating gate | 8 | O/C drill coverage, bound limits, source-review joins and denials |
| G606-05 assessment sources | 7 | R6 source coverage, comparative registration joins and denials |
| Full-runner tests | 7 | Source/suite binding and private-index denial |

I inspected the declared suite list, source-origin and stability checks,
authority fields, critical R2/R4/R5/R6 joins, and the named fault tests. The
314 cases are local synthetic test cases; they are not 314 independently
observed host runs or one actual production cohort. No provider credential or
paid send was used. No protected sampling registry, custodian mapping, label
store or outcome store was opened for this review.

## Supported claim and R0–R6 trace

The full runner verifies origins of fixed seed modules, follows local static
imports transitively (including package initializers), and hashes that source
closure before and after the suites. It also rejects a local module loaded
outside the closure, a changed closure, or a missing, failed, skipped or
incomplete suite. Its private index retains hashes and counts rather than
failure text or test output. The R6 fixture nests the R5 close, R4 trigger
reproduction, R3 attempt and end-to-end R2 screen. This establishes local
synthetic consistency for those fixture inputs. It does not authenticate all
external dependencies, independent anchors or actual operating evidence.

| Phase | Offline evidence inspected | Claim boundary and independent check |
|---|---|---|
| R0 fixture | [Integrated inert tests](../tests/test_cohort_r0_integrated.py) join assignment, claim, intent, audit, one entry, checkpoint and recovery; the fixed suite list also runs G6-02 through G6-05 faults. | Run on the exact target build with separately observed witness, checkpoint and stop behavior. The fallback fixture has a separate synthetic lineage. |
| R1 shadow | [Shadow tests](../tests/test_cohort_r1_shadow.py) check frozen scope, selected and unavailable exact routes, fallback lineage, stale control and empty dispatch state. The [shadow evaluator](../src/mos_eisley/run/cohort_shadow.py) is now source-bound. | Actual served-route observation and independent shadow review are absent. |
| R2 entry | [Entry validator](../src/mos_eisley/run/cohort_entry.py) reruns G605-06, joins a signed synthetic owner decision to the qualified scope and checks release, route, required paths and budget without mutation; [tests](../tests/test_cohort_r2_entry.py) deny changed inputs. The G606-02 screen binds signed R0/R1/on-call metadata to this result. | The fixture constructs its own evidence and keys. No actual G6-05 go, R0/R1 review, on-call attestation or owner/operator release was authenticated. `reviewable` grants no authority. |
| R3 attempt | [Per-attempt tests](../tests/test_cohort_r3_attempt.py) recheck R2 before a separate synthetic release, then join one assignment, claim, intent, audit and inert entry; cuts keep possible full exposure. | The guard is in a test fixture. The credential-owning live broker boundary, zero-retry transport and actual release procedure are unimplemented and untested on a target host. |
| R4 surveillance | [Inspector](../src/mos_eisley/run/cohort_surveillance.py) and [tests](../tests/test_cohort_r4_surveillance.py) join inert entries to claims/intents/audit, compute conservative exposure, and return warning, hard-stop or stopped findings. | The inspector reports a condition; it does not issue a stop. Live cadence, alert delivery, independent safety source and operator response are unmeasured. |
| R5 close | [Close validator](../src/mos_eisley/run/cohort_close_handoff.py) and [tests](../tests/test_cohort_r5_close_followup.py) reproduce an R4 trigger before close, bind the high-water state and closed release, keep the original roster and pending follow-up. The G606-02 screen binds a signed source bundle. | Fixture anchors and receipt digests are locally constructed. Independent freeze, close latency and source custody require observation; `reviewable` is not a close authorization. |
| R6 assessment | [Assessment validator](../src/mos_eisley/run/cohort_assessment_handoff.py) and [tests](../tests/test_cohort_r6_assessment_handoff.py) rerun the reproduced R5 handoff, bind the original denominator, separate inert-entry index, conservative cost and later-window references. The G606-02 screen binds a signed R6 bundle to R5. | Evidence references are synthetic digests. Quality, damage, completion, incident disposition, registration and any comparison need approved independent source review. No positive claim or next-cohort authority follows. |

The [G606-02 handoff validator](../tools/g6_06_handoff_evidence.py) adds a
separate metadata screen at both ends of this chain. At R2 it binds an exact
R0 index, complete R1 decision batch, base R2 result and on-call digest to a
frozen manifest/build, task coverage and trust roster. Distinct domain-separated
Ed25519 R0, R1 and on-call accept records must match the packet references,
source-set digests, ordering and decision window. At R6 it binds the R4 trigger,
pre-close state, recovery anchor, reproduction, closeout, R5 result, R6 packet,
evidence references, inert-entry index and reproduced R6 result through signed
R5 and R6 source-bundle reviews. Missing, rejected, stale, substituted or
wrong-key reviews block. These checks consume results from the existing
R2/R5/R6 validators; they do not replace those validators, authenticate the
underlying source artifacts or establish actual reviewer/key custody. The
synthetic fixtures construct their own keys and metadata.

## C01–C09 acceptance trace

The [plan's acceptance matrix](G6_06_BOUNDED_ROLLOUT_ASSESSMENT_PLAN.md#synthetic-rehearsal-and-target-host-acceptance-matrix)
requires an exact manifest/build, frozen failpoints and a separate observer.
The following are local negative oracles, not completed target-host cases.

| Case | Synthetic evidence | Target-host or source decision still required |
|---|---|---|
| C01 release/qualification | [R2 entry tests](../tests/test_cohort_r2_entry.py) deny missing go/review/on-call references, changed release and shadow elevation. | Verify real G6-05 go, signer custody and separate release. |
| C02 owner/roster/one use | [Controller tests](../tests/test_cohort_controller.py) deny duplicate and unassigned claims and keep the original roster. | Verify trusted enrollment, cross-owner isolation and no fresh-session cap escape on the chosen host. |
| C03 caps/crash | Controller tests exercise last-slot competition and assignment process cuts; [R3 tests](../tests/test_cohort_r3_attempt.py) retain post-claim exposure. | Inspect separate-process high-water, unresolved and three-scope totals after each cut. |
| C04 outages | [Audit/alert tests](../tests/test_cohort_audit_outage.py) deny lost required paths, expose missing joins and retain the one-entry race bound. | Prove independent audit/alert delivery, clock and stop latency. |
| C05 route change | [Route-change tests](../tests/test_cohort_route_change.py) cover pre-claim, post-claim and post-final-read loss plus exact fallback. | Verify live catalog/price/conformance observations and approved fallback on the target build. |
| C06 stop/re-entry | [Stop/re-entry tests](../tests/test_cohort_stop_reentry.py) cover three stop cuts, restart and same-epoch denial. | Measure signed stop acknowledgment, in-flight bound and recovery under distinct custody. |
| C07 early close/follow-up | [Early-close tests](../tests/test_cohort_early_close_followup.py) retain failed/cancelled tasks, unknown follow-up and lost local outcome-write status. | Independently inspect restricted follow-up and original denominator after the registered window. |
| C08 combined rollback | [Rollback tests](../tests/test_cohort_combined_rollback.py) detect restored stores against a supplied high-water anchor. | Prove the anchor is outside coordinated rollback custody and reconcile full possible exposure. |
| C09 freeze/assessment | [Freeze tests](../tests/test_cohort_assessment_freeze.py) deny policy/rubric substitution, early maturity and favorable subsets. | Review actual prospective registration, grading, unknowns and comparison eligibility in the audited workflow. |

## Findings and required disposition

| ID | Class | Finding and closure |
|---|---|---|
| G606-01 | Offline addressed; independent review open | The runner discovers local Python imports and package initializers transitively from fixed seeds, hashes the resulting 306-file closure before and after execution, and rejects newly loaded local modules outside it. The R1 shadow source, activation control, routing policy and routing protocol are included. Tests cover a newly imported transitive file and a dynamically loaded unbound module. The fresh 314-test run passed with stable sources. An independent reviewer must rehash and reproduce this worktree; external dependencies and separately executed processes need their own build/host checks. |
| G606-02 | Offline handoff checks addressed; independent source review open | The R0/R1-to-R2 screen binds the exact index/batch/base result and on-call digest to signed dated accept records, task coverage, source-set digests, manifest/build and frozen trust roster. The R5/R6 screen binds exact trigger, recovery, reproduction, closeout, assessment and evidence-reference digests to separate signed reviews. Six synthetic tests cover complete joins, changed index/batch/task coverage/result, missing/rejected/stale/wrong-key reviews, changed reproduction/evidence and rebound bundles. The source objects and reviewer keys are still fixture-constructed. Independently freeze and inspect real source artifacts, enroll distinct reviewers, verify custody and record dated accept/reject decisions before accepting either transition. |
| G606-03 | Offline validator and candidate package addressed; independent reproduction open | The [validator](../tools/g6_06_reproduction_handoff.py) compares a separately frozen baseline and fresh index, all 306 ordered source digests, 17 suite identities, case-ID digests/counts, lock/runner hashes, declared build/protocol/command digests, distinct producer/reproducer and host IDs, and the dated replay window. Six synthetic tests cover mismatches. The [local package](G6_06_G60603_REPRODUCTION_FREEZE.md) includes the exact source archive, fresh baseline, 314 case IDs, command/protocol digests and a self-run clean-extraction check. Its anchor template deliberately lacks external build, host, reviewer and freeze-window claims. A distinct reviewer must independently freeze those inputs, replay on the exact build, inspect discrepancies and record a dated disposition. These synthetic fixtures do not constitute a continuously operated cohort. |
| G606-04 | Offline screen and candidate handoff addressed; live operating gate open | The [validator](../tools/g6_06_operating_gate.py) joins one manifest/build/host/witness and frozen limits to the existing O01–O10 drill screen, exact C01–C09 fault matrix, bounded source-review rows and a separate anchor. Eight synthetic validator tests cover complete metadata, missing/failed faults, changed bindings, raised ceilings, weak exposure, stale/late freeze, rejected/rebound reviews, and a private result. The [candidate handoff](G6_06_G60604_OPERATING_GATE_HANDOFF.md) fixes 35 C-fault slots, five intentionally invalid strict templates and 19 O/C review slots; its 20-test preflight includes the G6-05 host-drill tests. Supplied reviewer and host identities and G5/G6 decision digests are unauthenticated metadata. G6-01 through G6-04 independent decisions, G5 qualification, G6-05 source/host review and owner go remain open. Execute O/C on the target host with actual witness/checkpoint, credential, audit, alert, route and stop topology; approve ceilings and the final-read in-flight bound before any bounded-live release. |
| G606-05 | Offline screen and candidate handoff addressed; assessment gate open | The [validator](../tools/g6_06_assessment_sources.py) reruns base R6 metadata checks, binds the reproduced R6 result, follow-up index, all eight R6 evidence references and upstream handoff digest to a separate frozen source-review roster. Nine accepted descriptive rows or eleven registered-comparison rows must cover the original task count without unknown/disputed entries; incident status and pre-cohort registration must match. Seven validator tests cover complete metadata and missing, rejected, substituted, partial, stale and rebound cases. The [candidate handoff](G6_06_G60605_ASSESSMENT_SOURCE_HANDOFF.md) has all 9/11 source slots, three invalid templates, a missing-input inventory and a 23-test preflight including R5/R6 handoff suites. Reviews and source custody remain supplied metadata; no protected labels/outcomes or sampling registry were opened. Independently inspect complete follow-up, incidents, restricted sources and any pre-registered comparison before a real decision. No probability, group, label or split may be inferred or repaired. |

**Technical conclusion:** the synthetic suites passed for the recorded local
worktree, and the phase validators preserve false authority fields. G606-01
through G606-05 have offline screens; independent reproduction, source review,
the live operating gate and actual cohort assessment remain open. This technical review
packet is complete as a handoff of evidence and findings; it closes no release
or assessment gate.

## Independent decision record to complete later

An absent field is **open**, never implied by `synthetic_pass` or `reviewable`.
Record only bounded metadata and keep underlying private evidence with its
approved custodian.

| Required decision field | Current value |
|---|---|
| G606-01 independent rehash and exact build/host confirmation | Open; same-preparer rehash matched, independent reviewer and build/host authentication absent |
| G606-03 frozen anchor, distinct replay, discrepancy disposition and authenticated reviewer/host | Open; local clean replay matched, no pre-replay independent anchor or separate host |
| G606-04 O/C target-host fault execution, source custody, signed reviews, ceilings and release | Open; offline packet screen and candidate handoff ready |
| G606-05 independent per-source review, mature follow-up, incident disposition and assessment | Open; offline coverage screen and candidate handoff ready |
| Named implementing owner, distinct technical reviewer and separation basis | Open |
| Frozen R0–R6 and C01–C09 protocol, resource ceilings and negative oracles | Open |
| G6-01 through G6-04 independent accept/reject references | Open |
| G5 qualified-policy claim and G6-05 independent source/host decisions | Open |
| R0/R1 observed results and distinct dated acceptance records | Open |
| R2 owner/operator release decision for one exact manifest and build | Open |
| R3/R4 target-host attempt, audit/alert and measured stop observations | Open |
| R5 original-roster close, source freeze and mature follow-up review | Open |
| R6 independent assessment, incident disposition and any registered comparison | Open |

Sampling receipts remain metadata only and grant no authority or holdout
assignment. This packet contains no prompts, transcripts, model responses,
tool output, protected outcomes or sampling assignments. Unknown probabilities,
independence groups, labels and splits remain unknown.
