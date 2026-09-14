# Changed-tree replacement verification

G1 replacement verification closes one work unit only after an explicit fresh
continuation has detected that the repository changed and made historical passing
checks stale. The boundary is implemented by
`ChangedTreeReplacementVerificationStore` in
`src/mos_eisley/task_state_replacement_verification.py`.

The store is an inert local-state publication boundary. It never executes a
command, starts a tool server, revives an approval or grants execution authority.
The caller must supply the completed work revision, current verification records
and immutable evidence artifacts produced by an independently authorized runner.

## Claim-bound transition

The store reopens and fully validates the exact current task-state selection,
owner-private continuation selection and canonical one-session claim. It replays
the selected archive, reproduces the live Git/main-file freshness inspection and
requires the result to match the claim's freshness digest. Closure is accepted only
when:

- at least one workspace dimension changed and the prior checkpoint contains a
  passing verification that the continuation marked stale;
- the proposed checkpoint retains the prior verification history in order, changing
  invalidated passes only to `stale`;
- at least one newly appended passing verification binds the exact live workspace
  and dirty-state input digests and has matching completed-work evidence;
- the selected queued or active work unit advances to one completed terminal
  revision with the ordinary checkpoint-closure lineage and outcome invariants;
- cumulative context, the aggregate task ledger, immutable inventories, remaining
  obligations and the checkpoint main-file inventory are preserved; and
- the continuation session, selections, archive, checkpoint, work-unit revision and
  freshness digest still match their pinned values.

This is replacement evidence, not reuse of a historical pass. A clean tree, missing
or failed replacement, wrong input digest, changed session, ledger reset or live
workspace race fails closed.

## Durable publication

Publication reuses the checkpoint store's private lock and compare-and-swap pointer
protocol. The complete next archive and new artifacts are saved and fsynced before
the current pointer changes. The claim, pointer and a second live inspection are
then rechecked; the canonical current selection is installed with one atomic
same-directory replacement and directory fsync. A crash before the pointer update
may leave an unselected immutable archive, which an exact retry verifies and reuses.
Conflicting content or a stale pointer is rejected.

The text-free receipt records the claim and freshness hashes, changed dimensions,
stale and replacement verification IDs, revision chains, remaining outstanding work,
aggregate ledger and cumulative-context digest. It explicitly records that the
historical passes were superseded, the replacement is current and no authority was
granted.

## Acceptance

`tests/test_task_state_replacement_verification.py` creates a real temporary Git
repository, records a clean passing checkpoint, changes both a tracked implementation
file and its tracked test, acquires a real fresh-context claim, runs that changed
test, publishes its output as current replacement evidence and verifies the atomic
archive/pointer transition. Negative fixtures reject blind historical-pass reuse,
missing replacement evidence, a wrong live input digest, a different claim session,
a workspace change between validation and pointer commit, and aggregate-ledger
reset. These tests establish controller enforcement, not provider quality or general
authority to run commands.
