# G0 milestone review: reconcile and instrument

## Disposition

Accepted as the offline contract and replay boundary required by plan §26.4.
G0 now supplies versioned clause, decision, outcome, work-unit, checkpoint,
context-measurement and task-profile records with deterministic negative fixtures.
It does not connect checkpoints to the conversation controller, compact author
context, start tools, dispatch a continuation or grant authority. Those remain G1.

The implementation follows the Python CLI and verification guidance from
[`production-project-template` commit `d59f3e6`](https://github.com/joshuamyers22/production-project-template/commit/d59f3e661a1fa3456505cf36f91b51f4a1c873ac),
which was verified as the latest published `main` revision on 2026-09-13.

## Objective and authority

- Requirement: `docs/mos-eisley-plan.md` §§6.6–6.7 and §26.4 G0.
- Owner and accountable decision authority: Josh Myers.
- Implementing agent: Codex, under the user's G0-only direction.
- Independent evidence reviewer: not required for this offline schema gate; the
  implementation received a bounded adversarial self-review against the frozen gate.
- Risk class: material data-integrity and private-storage boundary.
- Non-goals: all G1 runtime lifecycle behavior, live providers, executable checks,
  network probes, automatic rewrites and new credential paths.
- Resource ceiling: no paid/provider calls; at most three adversarial correction
  passes with focused checks after each, plus two full repository gates when the
  first exposes an environment constraint or precedes final hardening. Stop on a
  blocking data-integrity finding, unavailable locked gate or need to expand into G1.
- Rollback: remove the three new isolated modules, their tests, wheel-smoke
  registration and these G0 status updates. Existing run, conversation and provider
  schemas were not migrated.

## Acceptance evidence

| Gate | Evidence |
| --- | --- |
| Versioned shared records | Strict immutable clause, decision, outcome, input, evidence, work-unit and checkpoint contracts bind owner/project/workspace and exact revisions/digests. |
| Completion integrity | Active work requires current required inputs; completion requires current passing evidence and one exact terminal outcome. Resource use cannot exceed the recorded ceiling. |
| Bounded views | UTF-8 views bind the full artifact, stream, counts, policy and ordered omission ranges; replay mechanically reproduces visible content and rejects hidden loss. |
| Cumulative context | Every retained request contributes an exact category breakdown; checkpoint and handoff/revalidation input remain visible. Admission and confirmed/estimated/unavailable provider usage stay distinct, and aggregate totals are recomputed from request records. |
| Offline profile diagnostics | Required rule/tool omission, unknown required-tool availability, unavailable or unauthorized selected tools fail. Duplicate/temporary/unknown instructions, oversized root guidance, unused optional tools and overlap remain visible warnings. |
| Continuation validation | Offline selection rejects stale checkpoint/workspace or passing-test state, absent/extra inputs, terminal work, owner/project changes, and context or task-ledger resets. The selection grants no authority. |
| Private replay | Canonical manifest-last archives use mode `0700` directories and `0600` files, exact digest-named inventories, content hashes, duplicate-key rejection, bounded reads and owner/project/workspace checks. |
| Compatibility | A schema-1 recorded review run still round-trips through the existing replay path unchanged. |

## Adversarial findings

| Finding | Correction | Result |
| --- | --- | --- |
| Aggregate context totals could be asserted without request-level proof | Retain bounded request metrics and recompute every aggregate during bundle construction/replay | Resolved by negative fixture |
| Omission metadata did not prove that a visible view came from the retained bytes | Add exact content/count checks and deterministic byte-range reproduction from the digest-bound artifact | Resolved by reproduction and tamper fixtures |
| A valid manifest could coexist with untracked or publicly readable archive files | Require exact bounded directory inventories plus owner and permission checks on every replayed directory/file | Resolved by extra-file and mode fixtures |
| Interrupted writes could leave ambiguous state | Write into a private temporary directory, fsync files/directories, publish by rename, and treat the manifest as completion marker | Resolved by injected second-write failure |
| Evidence and continuation records admitted structurally valid but unrelated nested state | Require known requirement bindings, exact owner scope, nonterminal work and exact input inventories | Resolved by cross-scope, unknown-requirement, terminal and extra-input fixtures |
| A manifest could swap two digest-named paths while retaining a valid set of names and hashes | Bind every artifact path directly to the digest in its own manifest entry | Resolved by swapped-name fixture |
| Aggregate input bytes hid the categories required by the plan | Require each request's category sum to equal its local total and recompute cumulative categories and handoff overhead | Resolved by mismatch and aggregate fixtures |

No blocking finding remains from the bounded review. Same-UID replacement of a
trusted storage parent remains outside the existing process threat model. Filesystem
durability ultimately depends on the host filesystem honoring file and directory
`fsync`. G0 fixture enforcement establishes no live continuation quality, context
savings, provider usage, billing or authorization claim.

## Verification

Focused verification on 2026-09-13:

- `uv run --frozen ruff check` on the G0 modules and tests: pass.
- `uv run --frozen pyright` on the G0 modules and tests: pass, zero findings.
- `uv run --frozen coverage run --branch -m unittest tests.test_task_state_g0`:
  25 tests pass.
- Focused branch-inclusive coverage across the three G0 modules: 88%.
- Final `make check`: pass. Ruff and formatting are clean, Pyright reports zero
  findings, 2,243 source-tree tests pass with 4 skips at 89% repository coverage,
  runtime export verification and wheel build pass, and 1,646 installed-wheel tests
  pass with the G0 suite included.

The full gate emits one existing Pydantic serialization warning from conversation
tests involving a list where a tuple is expected. It does not fail the gate and is
outside this G0-only change.
