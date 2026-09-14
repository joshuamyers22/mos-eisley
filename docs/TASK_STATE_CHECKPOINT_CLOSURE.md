# Task-state checkpoint closure

G1 checkpoint closure advances one explicitly selected active work unit to one
terminal revision without granting continuation or execution authority. The boundary
is implemented by `TaskStateCheckpointStore` in
`src/mos_eisley/task_state_checkpoint.py` and builds on the G0 task-state bundle and
archive contracts.

The caller prepares a complete next `TaskStateBundle`, the bytes for newly referenced
artifacts, and the SHA-256 digest of the exact current-selection file it inspected.
Closure takes a private sibling lock, reopens that selection, replays its complete
content-addressed archive, and validates the proposed transition before writing. The
selection file and its parent directory must be owner-only because the lock,
temporary replacement and current pointer form one local compare-and-swap boundary.

## Accepted transition

One accepted closure must:

- increment the bundle and checkpoint revisions exactly once and bind both previous
  SHA-256 values;
- preserve the complete clause, accepted-decision, profile, work-unit, outcome and
  cumulative context history;
- append exactly one terminal revision of the selected active work unit and exactly
  its new outcome, without changing the unit's objective, scope, inputs,
  requirements, ceiling or authorization references;
- retain all prior evidence, use a nondecreasing task ledger, including attempts,
  correction/review counters and uncertain effects, and remove only the closed unit
  from the full outstanding-work set;
- retain active decisions, completed outcomes, untested claims, blockers and a
  disclosed short next-action view;
- for completed work, reproduce the G0 current-evidence rules and bind every required
  verification to a passing checkpoint verification for the new workspace state;
  and
- use the deterministic closure-lineage digest linking the prior bundle/checkpoint,
  terminal work and outcome, workspace, cumulative metrics, ledger and remaining
  obligations.

Blocked and cancelled units remain terminal outcomes, not successes. A blocked
closure must carry its terminal reason in the checkpoint blockers. Closure cannot add
an accepted decision, turn an untested claim into a fact, create new work, reset
counters, enable runtime continuation, or grant authority.

## Durable publication

The next archive is written and fsynced through the existing immutable G0 store before
the current pointer changes. The exact old selection digest is checked under the
exclusive lock and checked again after archive persistence. The new canonical
selection is installed with one same-directory `os.replace` and the directory is
fsynced. A stale or concurrent writer, duplicate closure, missing artifact, invalid
transition or changed pointer leaves the old selection authoritative.

If a crash leaves the exact proposed immutable archive durable before pointer
replacement, a retry verifies and reuses that archive; conflicting content is
rejected. A successful receipt is text-free, records both revision chains and the
new selection digest, and explicitly says that no continuation was claimed and no
authority was granted.

Closure itself does not inspect the live Git tree, mark old tests stale after changed
inputs, select or claim a fresh continuation, compact author context, publish project
memory, or emit pressure indicators. The separate
[fresh-context continuation boundary](TASK_STATE_CONTINUATION.md) now performs the
inspection, stale disclosure and claim only after an explicit selection. The
[changed-tree replacement-verification boundary](TASK_STATE_REPLACEMENT_VERIFICATION.md)
then reuses this archive/pointer protocol to close the claimed unit only with exact
current evidence; compaction, memory publication and pressure indicators remain
separate boundaries.

## Acceptance

`tests/test_task_state_checkpoint.py` covers successful archive/pointer publication,
exact orphan recovery, stale and duplicate closures, concurrent locking, missing
artifacts, lost pending work, cumulative-context and ledger resets, uncertain-effect
loss, unaccepted decision promotion, missing or non-passing verification, hidden
untested claims and nonprivate selection storage. These are controller enforcement
fixtures; they are not live quality or provider evidence.
