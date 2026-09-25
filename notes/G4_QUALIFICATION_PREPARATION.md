# Work Note: first G4 qualification preparation

- Status: offline input/custody checkpoint complete; execution qualification open
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
- Non-goals: actual child/critic/judge call, execution grants, spending, final G4 pass.
- Risk: high. Offline resource ceiling: zero provider micro-USD and no credential
  access; one exact image build, local source-level draft controls and offline
  input/custody signing. Stop at a failed identity, signature or package check.
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

## Handoff

- Current state: exact signed creator approval, frozen reviewer package and
  signed single-operator custody verify. There is no execution grant, provider
  call, authenticated control receipt or final G4 evidence.
- Next smallest safe action: prepare immutable implementation binding for
  declared known-good/known-bad trees and run the paired isolated offline
  controls in the pinned image; no candidate dispatch yet.
- Blocker and required authority/input for later live stages: assignment/result
  and VCS provenance, second provider family, live spending/dispatch approval,
  shared ledger and applicable G3 gate.
- Checks already run: controller image start/source hash; clean target Git;
  local draft good/bad creator/reviewer test sensitivity; canonical creator and
  custody signatures verified; package freezer/replay passed; product source
  `make check` passed on `752c350` before this docs-only preparation.

## Close and promote

- Outcome: complete offline input/custody checkpoint, not execution
  qualification or launch authority.
- Durable fact promoted to `PROJECT_MEMORY.md`: none; project memory is not an
  index of ephemeral exercise status.
- Temporary artifacts removed: generated Python bytecode caches from target
  and reviewer draft; both can be regenerated.
