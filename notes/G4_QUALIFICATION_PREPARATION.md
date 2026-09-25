# Work Note: first G4 qualification preparation

- Status: two failed receipts, signed triage, zero-spend cycle-1 admission and offline dispatch grant verified; child execution and qualification open
- Owner: Joshua Myers
- Started (UTC): 2026-09-25
- Last updated (UTC): 2026-09-25
- Review or delete by: first G4 qualification decision
- Related plan: [G4 roadmap](../docs/ROADMAP.md) and
  [qualification packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md)

## Objective and completion evidence

- Intended outcome: a reproducible, bounded first correction-path exercise with
  exact controller image and isolated target, no premature live authority.
- Invariants: clean source/target Git identities; blind tests outside target;
  single-operator human roles disclose self-review and use a child-distinct key;
  one-use claims and ledger before any call; no seeded
  initial child presented as a real provider child; G3 remains separate.
- Non-goals: actual child/critic/judge call, correction dispatch, provider
  spending, final G4 pass.
- Risk: high. Offline resource ceiling: zero provider micro-USD and no credential
  access; one exact image build, local source-level checks, offline
  input/custody signing and paired no-network container controls. Stop at a
  failed identity, signature, package or receipt check.
- Selected pinned guidance: `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md` and
  `templates/WORK_NOTE.md`. The template provenance is in `AGENTS.md`.

## Context retrieved

[G4 package](../docs/G4_REVIEWER_TEST_PACKAGE.md),
[binding](../docs/G4_IMPLEMENTATION_BINDING.md),
[controls](../docs/G4_ISOLATED_TEST_EXECUTION.md),
[custody/Git](../docs/G4_AUTHENTICATED_PROVENANCE.md),
[candidate](../docs/G4_CANDIDATE_EXECUTION.md),
[correction](../docs/G4_BOUNDED_CORRECTION.md),
[broker](../docs/G4_PRODUCTION_CODING_CHILD_BROKER.md),
[final suites](../docs/G4_FINAL_WHOLE_SUITES.md), and
[independent review](../docs/G4_INDEPENDENT_REVIEW.md).

## Observations and attempts

| Time (UTC) | Type | Observation, action or result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-25 | observation | Existing `mos-eisley:local` image was the old G2 image; product source was clean at `752c350`. | Image inspection and Git | Build exact G4 image. |
| 2026-09-25 | attempt | Network-disabled Docker build stopped while fetching pinned `uv`; no image was produced. The unchanged pinned Dockerfile then built successfully with package downloads. | Packet image ID and build result | Verify image. |
| 2026-09-25 | observation | New `linux/arm64` image ID is pinned; read-only/no-network CLI starts and installed G4 gate bytes match the host source. | [Packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Prepare target. |
| 2026-09-25 | action | Created a separate clean detached controller worktree at exact commit `752c350`; documentation work stays on `docs/g4-qualification-preparation`. | Git worktree/status | Preserve exact runtime source. |
| 2026-09-25 | decision | User selected an isolated disposable target rather than a product change. | User direction | Keep blind tests outside target. |
| 2026-09-25 | observation | Isolated target base is clean at `699f345`; the seed fails two creator assertions, known-good passes both five-test suites, and known-bad fails by assertion with zero errors. These are not authenticated G4 receipts. | Target Git and local checks | Seek exact plan/test approval. |
| 2026-09-25 | decision | Owner approved exact draft `PLAN.md` and protected creator `tests/test_quote.py` in chat, with a $10 task-wide cap (10,000,000 micro-USD) and 2026-09-26 23:59 America/Indiana/Indianapolis deadline. This is not a signed creator artifact or live grant. | User direction; exact hashes in packet | Review remaining inputs and establish authenticated custody. |
| 2026-09-25 | decision | Joshua personally reviewed interface, rubric and reviewer-test draft, accepted schema-2 self-review risk, and attested no implementation/telemetry exposure before reviewer review/freeze. The draft remains agent-authored; independent human review is not claimed. | User statements | Enroll exact role keys. |
| 2026-09-25 | action | Enrolled Joshua's supplied Ed25519 public key across single-operator human roles and generated a distinct owner-only, task-scoped child key. Validated policy SHA-256 `5991c355…`; no human private key was supplied to the assistant. | Private policy and key permissions | Owner signs exact creator approval. |
| 2026-09-25 | observation | Joshua signed creator approval locally; canonical artifact `419e2e0b…` and Ed25519 signature, policy, hashes and base revision verified. | [Packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Freeze package. |
| 2026-09-25 | observation | Pinned offline freezer emitted package `dad5e14a…`, payload `3f2bd652…`, one test file, five expected executions, no markers or downstream authority; replay passed. | [Packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Owner signs custody. |
| 2026-09-25 | observation | Joshua signed reviewer custody locally; canonical artifact `c5d9b2a7…` and Ed25519 signature, UTC chronology, creator/package links and self-review disclosures verified. Package replay passed again. | [Packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Bind source and run known controls. |
| 2026-09-25 | attempt | V1 known-good request was first rejected as noncanonical; after correction its no-network worker exited without a receipt. Local diagnostic reproduced a non-importable `unittest` start directory under the v1 collection settings. Lifecycle evidence retained; v1 is not qualifying evidence. | Private handoff and lifecycle record | Correct package collection setting and require new custody. |
| 2026-09-25 | action | V2 package changed only collection top-level directory, keeping reviewer test bytes and creator references. Distinct clean good/bad fixture commits and v2 bindings replay-verified. Joshua signed v2 custody; signature and exact package links verified. | [Packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Run paired controls. |
| 2026-09-25 | observation | Pinned no-network image ran 5/5 good tests with zero failures and 5/5 bad tests with two assertion failures, zero errors. Both exact receipts and paired record `ad304e15…` replay-verified; no candidate/provider execution or spend. | [Packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Authenticate child assignment/result and VCS/E2 provenance. |
| 2026-09-25 | decision | Joshua selected an explicitly seeded offline initial-child result. It cannot qualify real initial-child dispatch. | User direction | Prepare a zero-spend assignment for owner signature. |
| 2026-09-25 | observation | Joshua signed exact seeded assignment `63cbd8e5…`; verified canonical signature, scope, creator-test inventory, v2 custody/package and zero provider spend. | Private assignment and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Create disclosed fixture lineage. |
| 2026-09-25 | action | Disposable target branch has base `699f345` → assistant-authored partial child `89dc94d` → host README handoff `6f2551d`. Local creator test ran 5/5 with one expected half-up assertion failure; no candidate receipt. Task-scoped key signed result `dd4e16e2…`; custody chain verified. | Target Git and private result | Bind source and reconstruct Git. |
| 2026-09-25 | observation | Binding `97eee7ad…` replay-verified; read-only Git reconstructed exact ancestry, owned patch, committed blobs and clean source in unsigned claim `d59411ec…`. Strict CLI needed a separate canonical copy of the unchanged policy; original preserved. | Private binding/Git claim and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Obtain Joshua's separate VCS signature, then assemble/replay. |
| 2026-09-25 | observation | Joshua locally signed the exact Git claim; signed artifact `ad35ad0b…` verified against the enrolled VCS key. Assembled record `cb4dc4fb…` replay-verified against the clean target, v2 package, final binding and paired controls. All downstream authority remains false. | Private signed artifact, record and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Seek separate candidate-test admission. |
| 2026-09-25 | observation | Joshua signed exact one-use candidate approval. Admission `d2bb3486…` passed, and the no-network dispatch consumed one claim. Receipt `6d08b811…` replay-verified against the clean target: 5/5 tests, two expected assertion failures, zero errors, `candidate_tests_passed=false`. No correction or acceptance authority. | Private admission, claim, receipt and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Seek a separate signed grant for the second independent candidate. |
| 2026-09-25 | observation | Joshua signed distinct candidate-2 grant. Admission `bec6ecad…` passed; one no-network dispatch consumed a second claim in the same store. Receipt `43c2e9d8…` replay-verified against the clean target: 5/5 tests, the same two assertion failures and zero errors. The correction-gate pair validator accepted independent identities and matching failure IDs. This is reproduction, not defect adjudication or correction approval. | Private request, admission, claims, receipts and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Adjudicate both failed IDs with exact plan and implementation evidence. |
| 2026-09-25 | observation | Creator-signed plan `90dfdbea…` requires `(numerator + 5_000)//10_000`; bound source `496e2a33…` omits the increment at line 20. Frozen test expectations match the plan: tie inputs require 2/3 but source returns 1/2; discounted 707-cent subtotal requires 601 but source returns 600. Both failed IDs are source-level `implementation_defect` findings sharing one root cause, not evidence of a discount-order defect. No correction review policy, critic artifact or signed judge triage exists. | Owner-only `SOURCE_ADJUDICATION.md` and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Obtain accountable review and formal critic-bound judge triage before a correction grant. |
| 2026-09-25 | observation | A same-agent adversarial pass checked oracle, plan, order, source, flake and unreached-second-assertion alternatives. Owner-only critic artifact `4f6962f9…` is expressly non-independent; proposed canonical single-operator judge policy `55d29e01…` enrolls Joshua's existing public key and denies dispatch/acceptance. The local signer replayed both receipts and current Git and reached exact triage payload in a deliberate refusal without accessing Joshua's key. My direct source probe had created two ignored bytecode files; they were moved recoverably out of the source root before the signer preflight passed. No signed triage exists. | Private critic, policy, signer and `PREPARATION.md` | Joshua reviews exact inputs and signs locally if accepted. |
| 2026-09-25 | observation | Joshua locally signed triage artifact `aa87ff09…`. Canonical decode, Ed25519 verification against the enrolled judge key, both exact receipt hashes and failure IDs, critic/source evidence hashes, policy window and disabled dispatch/acceptance flags all passed. This is disclosed single-operator review with an agent-authored, non-independent critic pass; it is not a creator correction-cycle approval. | Owner-only signed triage and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Seek a separate creator-signed bounded correction-cycle approval and one-use admission. |
| 2026-09-25 | observation | Owner-only cycle signer preflight replayed exact receipts/current Git and checked the protected plan/tests, signed triage, source/critic evidence, scope, zero-spend child allowance, $10 task ceiling and deadline without key access or claim consumption. Joshua then signed approval `07e21f2c…`; enrolled creator signature and exact links verified. One pinned controller admission wrote `ad4fb9e9…` and exactly one matching private claim, both replay-verified. No dispatch, provider, write or acceptance authority. | Private signed approval, admission, claim and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | Consider a separately authorized exact correction-child dispatch; this cycle permits no provider spend. |
| 2026-09-25 | observation | Joshua signed separate offline correction-child dispatch grant `da0f4a2e…` binding admission `ad4fb9e9…`, current source, image `462ab0f7…`, only `src/quote_lab/price.py`, reviewed brief/criteria and creator-test byte view `2f0a5781…`. Canonical creator signature and read-only offer preview `418e0181…` verified against current Git; the image remains present as linux/arm64. No dispatch claim, child proposal, provider call or host write exists. | Owner-only signed grant, brief/criteria and [packet](../docs/G4_QUALIFICATION_PREPARATION_2026-09-25.md) | If instructed, execute one contained zero-spend offline dispatch; do not assume signing itself invoked a child. |

## Handoff

- Current state: signed creator/reviewer custody, distinct fixture bindings,
  paired control receipts, seeded assignment/result/VCS provenance and two
  matching failed candidate receipts replay, signed triage, one zero-spend
  correction-cycle admission and a separate offline child-dispatch grant.
  Both failed IDs trace to one missing half-up increment in the bound source.
  Both candidate claims and the cycle claim are
  spent. No real child dispatch, provider call or final G4 evidence.
- Next smallest safe action: execute one contained offline correction-child
  dispatch under the signed grant if instructed; no
  provider send without separate authorization.
- Blocker and required authority/input for later live stages: correction-child
  dispatch; a fresh nonzero-spend chain, second provider family, live
  spending/dispatch approval, shared ledger and applicable G3 gate.
- Checks already run: controller image start/source hash; clean target Git;
  local draft good/bad creator/reviewer test sensitivity; canonical creator and
  v2 custody, seeded assignment/result signatures verified; package, bindings,
  controls, authenticated Git/current-source and both candidate receipt replays
  passed; product source `make check` passed on `752c350` before this docs-only
  preparation.

## Close and promote

- Outcome: offline input/custody, paired controls, seeded VCS/E2 provenance and
  two independent failed-candidate reproductions, source-level assessment and
  signed triage plus one zero-spend correction admission complete; not correction
  qualification or launch authority.
- Durable fact promoted to `PROJECT_MEMORY.md`: none; project memory is not an
  index of ephemeral exercise status.
- Temporary artifacts removed: generated Python bytecode caches from target
  and reviewer draft; both can be regenerated.
