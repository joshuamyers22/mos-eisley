# G1 admission slice review

## Disposition

Implemented as bounded G1 admission, acquisition, closure, continuation,
context-pressure and validated-author-compaction increments,
not accepted as the complete G1 milestone. The recorded conversation controller can
consume one exact owner/workspace-scoped task profile and bind its material to request admission. It can
also acquire that profile automatically at each request boundary from an explicitly
selected frozen creator/coder guidance context. A separate current pointer can now
acquire bounded temporary task state from one verified G0 archive, and a closure
boundary can advance that pointer after one verified terminal work revision. An
explicit selection can now bind a fresh recorded session to one outstanding work
unit with live Git/file freshness and stale-test disclosure. `/status` and `/context`
now expose versioned advisory-only context pressure. Explicit author compaction is
reconstructable, source/lineage/freshness bound, hard-limit admitted and unavailable
to critics/judges. Validated semantic task discovery now selects one frozen author
packet for exact queued text with source-anchored evidence and complete omissions.
Runtime tool-catalog selection now exposes only exact-task schemas from one
byte-pinned approved catalog. Claim-bound changed-tree replacement verification now
requires current passing evidence before completing the continued work and atomically
publishing its checkpoint. Executable tool capability is not enabled.
Continuation approvals are now treated as expiring, revocable evidence bound to the
exact work subject and revalidated at claim and request boundaries; they grant no
execution authority.

The increment follows the small walking-skeleton, evidence and stopping guidance in
[`production-project-template` commit `d59f3e6`](https://github.com/joshuamyers22/production-project-template/commit/d59f3e661a1fa3456505cf36f91b51f4a1c873ac),
verified as the latest published `main` revision on 2026-09-13. It is stacked on the
G0 task-state branch because that contract is still under review in
[PR #223](https://github.com/joshuamyers22/mos-eisley/pull/223).

## Objective and boundary

- Requirement: `docs/mos-eisley-plan.md` §6.7, §26.4's first G1 ordering step,
  and the task-lifecycle/context-selection cases in §26.5.
- Owner and accountable decision authority: Josh Myers.
- Implementing agent: Codex, under the user's direction to begin G1.
- Risk class: material prompt-integrity and private-state admission boundary.
- Resource ceiling: no paid/provider calls; bounded admission, acquisition and
  checkpoint-closure, fresh-continuation, pressure-indicator, author-compaction,
  semantic-discovery, runtime-tool-selection and changed-tree-replacement slices,
  stale-approval handling, focused tests and the repository's full locked gate. Stop
  before adding executable tools or execution authority.
- Rollback: remove runtime materialization, optional preview/admission fields and the
  separate closure/continuation modules and their launch options. Legacy serialized
  admissions omit the optional fields and remain unchanged; prior task-state archives
  stay immutable.

## Implemented contract

- Exact selected guidance and tool definitions must match their manifest IDs,
  ordering, UTF-8/canonical byte sizes and SHA-256 digests.
- A selected temporary-state instruction, missing required profile material,
  unavailable/unauthorized selected tool, unrelated schema, or owner/workspace
  mismatch fails before the model attempt.
- Preview and saved admission bind the same exact model-request digest, profile
  diagnostics and work-unit revision.
- Reusable memory remains in its private conversation-memory artifact and is bound
  only by that artifact's digest. Temporary task state uses a distinct private entry
  artifact and source digest.
- Native JSON reconstruction and SQLite archival revalidate profile scope and the
  saved memory-context binding.
- Selected tool definitions are visible to the model as schemas, but the recorded
  controller retains a zero tool-call limit and the runtime profile dispatcher
  always refuses execution. Profile and admission records grant no authority.
- An explicit launch selection pins one frozen creator/coder packet and work-unit
  revision. Each non-review request revalidates current project identity, complete
  assessment, exact private policy and immutable context under the guidance lock,
  then releases the lock before dispatch. Review requests never acquire author
  guidance, and directory switches clear the selection/policy paths.
- Acquired profiles materialize the selected rule text, applicability, rationale,
  checks and approved override reasons. Text-free acquisition evidence records the
  selection, context, assessment and policy hashes plus explicit omitted requirement
  IDs. No private policy prose, task state or unselected source text enters the model
  request.
- Optional runtime tool selection byte-pins a separate approved catalog and complete
  exact-task decisions. It rechecks catalog/project/policy/profile/work identities,
  canonical schema metadata, required/optional selection and availability before
  exposing only selected definitions. Unselected definitions remain out of the
  request, no server starts and no dispatch is enabled. See
  [the runtime tool contract](TASK_TOOL_CATALOG.md).
- An owner-only launch pointer pins one immutable G0 task-state archive. Every
  non-review request requires that pointer to remain unchanged, fully replays the
  scoped archive, and materializes the checkpoint, its current work unit, applicable
  clauses and active decisions under a 256 KiB bound.
- Temporary task state is persisted as a separate SQLite entry artifact and bound to
  the exact request and matching task profile. Evidence identities and freshness stay
  visible, while evidence-view text is omitted with explicit IDs. This proves archive
  integrity and pointer stability, not live repository/test freshness or a claimed
  continuation. See [the task-state contract](TASK_STATE_ACQUISITION.md).
- Checkpoint closure compares against the exact selected pointer, fully replays the
  old archive, preserves immutable inventories, outstanding work, cumulative context,
  task counters and uncertain effects, and appends only the selected active unit's
  terminal revision and outcome. Completed closure requires current passing evidence
  bound to the new checkpoint workspace. The next archive is durable before one
  atomic pointer replacement; duplicate/concurrent writers and conflicting orphan
  archives fail closed. Its receipt grants neither continuation nor authority. See
  [the closure contract](TASK_STATE_CHECKPOINT_CLOSURE.md).
- Explicit fresh continuation replays that exact archive, reproduces the G0
  checkpoint/work/input/context/ledger selection, inspects the live Git repository
  and main files, and atomically claims the handoff for one fresh conversation.
  Changed workspace dimensions supersede historical passes with explicit stale IDs;
  missing inputs/evidence/files remain blockers. Same-session retry is idempotent,
  while duplicate/concurrent sessions, changed selections and mid-claim workspace
  changes fail closed. The bounded context and saved admission disclose the claim but
  grant no tools or execution authority. See
  [the continuation contract](TASK_STATE_CONTINUATION.md).
- Referenced continuation approvals are owner/workspace scoped, byte-pinned and bound
  to the immutable work subject, evidence source and exact ordered action set. Missing,
  mismatched, not-yet-valid, expired or revoked records fail before a claim; approval
  expiry is checked again after the claim and before every request. A fresh session
  cannot revive an expired record, and neither replay nor session reset extends its
  absolute UTC lifetime. Approval records remain evidence only and grant no execution
  authority. See [the approval-freshness contract](TASK_STATE_APPROVAL_FRESHNESS.md).
- The version-3 `/context` preview and new `/status` report expose the exact upcoming
  request's non-overlapping byte categories, both available-capacity calculations,
  growth since the checkpoint/session boundary, cumulative provider-known/unknown
  token observations, substantial-call count, repeated reads and compaction count.
  Threshold and counting rules are versioned and configurable within the adopted
  evaluation ranges. Crossing events are content-free, de-duplicated, capped per
  terminal run and never persisted as transcript messages. They take no action and
  grant no authority. See [the pressure contract](CONTEXT_PRESSURE.md).
- `/compact FILE` is an explicit two-phase author-only boundary. It retains the
  newest completed user instruction and steering ancestry verbatim, renders sourced
  semantic state only as an untrusted assistant derivative, records complete
  omissions and a private exact reconstruction artifact, and binds prior lineage
  plus a double-checked Git/file inspection. It requires an actual byte reduction,
  pre-admits both hard request limits, restores prior state on failure and permits at
  most three compactions. Reviews never receive it. See
  [the compaction contract](AUTHOR_COMPACTION.md).
- A semantic discovery plan maps exact queued-message digests and quoted character
  ranges to one of at most 16 frozen creator/coder profiles. It requires a complete,
  reasoned candidate partition, revalidates only the selected guarded role context,
  persists text-free evidence and never selects tools or grants authority. Reviews
  never acquire it. See [the discovery contract](TASK_SEMANTIC_DISCOVERY.md).
- A runtime tool plan maps the same exact queued-message identity to a complete
  ordered catalog decision, then composes with the guarded author profile at the
  request boundary. Required omission, selected unavailable/unauthorized tools,
  stale catalog bytes or altered schema metadata fail before an attempt. Its saved
  evidence is text-free, and the recorded controller retains a zero tool-call limit.
- Changed-tree replacement verification reopens the exact private selections and
  canonical continuation claim, reproduces live Git/main-file freshness and requires
  every invalidated historical pass to remain visible as stale. Newly appended
  passing records must bind the exact claimed workspace and input digests and matching
  completed-work evidence. The claimed queued or active unit then closes under the
  ordinary lineage, immutable-history, obligation, cumulative-context and aggregate-
  ledger invariants before durable archive publication and one atomic current-pointer
  replacement. The boundary executes no command and grants no authority. See
  [the replacement-verification contract](TASK_STATE_REPLACEMENT_VERIFICATION.md).

## Acceptance evidence

Focused fixtures cover exact preview/request/admission equivalence, separate private
memory binding, tampered-memory rejection, fail-closed diagnostics, descriptive-only
tool schemas, temporary-state rejection, unrelated-schema rejection, cross-scope
rejection, request-rebinding rejection, JSON round-trip and SQLite archive retention.
Runtime catalog fixtures additionally cover exact task/catalog/schema binding,
complete omissions and failure before attempts for required, unavailable or
unauthorized selections.

The bounded adversarial review found that callers could bypass construction-time
Pydantic validation with `model_copy` or `model_construct`. Controller scope
validation and final admission now reconstruct and revalidate the full runtime
profile before use; forged instruction content, tool schemas and failing diagnostics
are rejected before an attempt. Negative fixtures cover those paths.

The complete G1 acceptance demonstration remains open for conversation-to-review and
cancel/resume. Changed-tree replacement is now demonstrated with a real Git repository
and an actually executed changed test; stale-approval handling proves absolute expiry,
revocation and exact-subject binding across claims, retries, fresh sessions and request
dispatch. Author-compaction fixtures cover reconstruction and overflow-stop behavior.
Fresh continuation preserves obligations/aggregate ledgers and rejects duplicate
handoffs, while pressure indicators remain advisory. Fixture enforcement is not the
full end-to-end milestone or live quality evidence.

## Verification

Verification on 2026-09-14:

- Focused Ruff and formatting checks: pass.
- Focused Pyright: pass with zero findings.
- Current task-state acquisition: 14 focused tests pass. The profile/state admission,
  G0 replay, context, CLI and persistence compatibility set passes 166 tests.
- Checkpoint closure: 15 focused lifecycle/publication tests pass.
- Fresh-context continuation: 20 focused claim/freshness/admission tests pass;
  all 74 task-state tests and 974 conversation compatibility tests pass.
- Context pressure: 9 focused accounting/policy/CLI/TUI tests pass; the 74-test
  pressure and adjacent admission/continuation compatibility set passes.
- Validated author compaction: 7 focused reconstruction, authority, persistence,
  freshness, overflow, request-admission and terminal-control tests pass; the
  39-test context/pressure compatibility set passes.
- Validated semantic task discovery: 9 focused exact-selection, source-binding,
  review-isolation, persistence, tamper and terminal tests pass; the complete
  101-test task compatibility set and 59 adjacent context/admission tests pass.
- Runtime tool-catalog selection: 8 focused request-selection, required-tool,
  availability, authority, catalog-freshness, inventory, review-isolation and
  terminal tests pass.
- Changed-tree replacement verification: 7 focused real-Git completion, stale-pass,
  missing/wrong replacement, claim-session, workspace-race and ledger-preservation
  tests pass; all 81 task-state tests pass.
- Stale approval handling: 9 focused exact-binding, missing, revoked, mismatched,
  edited-selection, fresh-session non-revival, same-session expiry, mid-claim expiry
  and per-request dispatch-prevention tests pass; the 36-test continuation,
  approval and replacement set and 102-test compatibility set pass.
- Full G1 stack `make check`: pass. Ruff and formatting are clean; Pyright reports
  zero findings. The 2,359 source-tree tests run successfully with 4 skips at
  89% repository coverage, and runtime export verification and package builds pass.
  The installed-wheel run,
  including all eleven G1 profile-admission, profile-acquisition, task-state,
  closure, continuation, pressure, compaction, discovery, tool-catalog,
  changed-tree-replacement and stale-approval suites plus all five editable
  selection fixtures, passes all 1,762 tests.

The full gate emits the existing Pydantic serialization warning documented in the
G0 review. It does not fail the gate and is outside this increment. No live provider
or paid request is part of this slice; provider-looking HTTP logs come from the
repository's mocked transport fixtures.
