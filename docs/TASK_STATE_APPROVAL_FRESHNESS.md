# Task-state approval freshness

G1 continuation treats `WorkUnitRecord.authorization_refs` as mandatory references
to explicit, time-bounded approval evidence. This boundary prevents a new or resumed
conversation from reviving an approval that has expired. It does not add an
execution path, tool permission, credential, spending permission or automatic
replay mechanism.

## Contracts and launch

`TaskApprovalRecord` binds an approval identity and source digest to one
owner/project/workspace scope, exact work-unit identity and revision, immutable
planning-subject digest, bounded action labels, issue time and expiry. Both times
must use an explicit UTC offset, and expiry must follow issue time. The record
states that session reset does not extend expiry and automatic replay is false.

`TaskApprovalSelection` is canonical JSON containing bounded approval records and
explicit revocations. It and its parent directory must be private and owner-only.
Its exact launch bytes are pinned. Supply it only with fresh continuation:

```sh
mos --plain -C /path/to/project \
  --task-state-selection /private/current-task-state.json \
  --task-state-continuation-selection /private/continue.json \
  --task-approval-selection /private/task-approvals.json \
  --task-state-storage /private/task-state-archives
```

The work unit stores each required record's canonical SHA-256 digest in
`authorization_refs`. The subject digest excludes those references to avoid a hash
cycle, but includes the work revision, scope, dependencies, objective, component and
interface boundaries, clauses, direction and policy digests, inputs, evidence
requirements, stopping condition and resource ceiling. Editing any of that planning
identity requires a new matching approval record.

## Fail-closed acquisition

For approval-bound work, continuation acquisition reopens the pinned file and
checks every required reference. It rejects missing, revoked, not-yet-valid,
expired or mismatched records before creating a claim. It then binds the selection
digest and ordered authorization references into the durable one-session claim.
After the claim, it reopens and rechecks the approval selection before returning any
runtime context. If expiry crosses during that interval, the claim may remain as
non-authoritative crash evidence, but no runtime context reaches model dispatch.

The recorded controller reacquires task state before each author request, so an
approval that expires after a successful request blocks the next request. The check
always compares an absolute UTC time with the record; a fresh session, resumed
session, context compaction or same-session retry cannot reset the clock. The
runtime context retains only text-free freshness evidence, not the source approval
record.

All approval records, selections, freshness evidence and continuation claims have
`grants_authority: false`. This slice verifies whether referenced external approval
evidence is still current; actual side-effect execution remains outside G1, and an
uncertain operation is never replayed automatically.

## Acceptance

`tests/test_task_state_approval.py` covers exact current approval binding, missing
selection, explicit revocation, wrong-work binding, pinned-file mutation, expiry
before a new-session claim, expiry during claim, same-session expiry, per-request
revalidation and failure before recorded dispatch or attempt consumption.
