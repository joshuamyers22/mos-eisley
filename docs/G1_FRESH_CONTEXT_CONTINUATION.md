# G1 fresh-context continuation

## Status

Implemented on 2026-09-20 as the third G1 runtime slice in plan §6.7.2 and §26.4.
An explicitly selected checkpoint next action can now be claimed by one fresh
conversation, materialized as bounded task context, revalidated immediately before
request admission, and recorded without turning checkpoint state into reusable
memory or granting execution authority.

## Selection and durable claim

`ContinuationSelection` names the exact owner/project/workspace scope, checkpoint
ID, revision and digest, one advertised next work unit, its complete required-input
inventory, the checkpoint workspace, and the original cumulative context and
resource-ledger baselines. `ConversationController.submit_continuation` accepts the
selection with the user's continue request and queues it without another
confirmation. Its lower-level `begin_continuation` seam accepts that selection only
while the conversation has no message history.

The scope-bound checkpoint store fully replays the immutable task archive and its
evidence before claiming. It rechecks the current head, selection, required inputs,
branch, revision, tree and dirty-state digests. Passing verification records are
rebound to the observed workspace and input digest; a changed workspace reports the
verification IDs that became stale. Unresolved uncertain effects stop selection so
the new session cannot silently replay them.

One canonical, private claim is atomically published per checkpoint digest. Its ID
binds the selection and fresh session ID. Retrying the identical claim in the same
session returns the same receipt; a different session or work-unit selection is
rejected. The checkpoint remains intact on every rejection.

## Fresh bounded context and admission

The materialized context contains only the selected checkpoint view, selected work
unit, applicable plan clauses, active decisions, verification metadata, disclosed
untested claims and blockers, and preserved lineage. Contract limits and a hard
serialized-context ceiling bound it. It contains no prior conversation transcript.
Reusable user/project memory remains separately classified.

Before each provider request, the controller observes the workspace again, reloads
the current checkpoint and durable claim, and reproduces the context digest. A
changed head, workspace, evidence binding, claim or lineage leaves the request
queued and consumes no recorded exchange. If a task profile is present, it must
select the same work unit and still passes the existing current-policy, instruction,
tool-schema and authority admission checks.

The schema-3 continuation receipt remains nested in current schema-6 request
admission, and schema-2 context classification marks the exact claim as
checkpoint-selected. The system
request receives the bounded checkpoint JSON with an explicit statement that it is
task state, not reusable memory or new authority. Closing the next milestone clears
the active claim while historical request admissions retain their provenance.

## Acceptance coverage

Deterministic fixtures cover successful fresh-session dispatch, saved-state replay,
same-session idempotency, cross-session duplicate claims, non-fresh history,
post-claim branch changes, stale verification reporting and no-dispatch behavior.
The installed-wheel smoke suite includes these tests.

## Completed G1 connections

Author compaction/reconstruction is implemented in `G1_AUTHOR_COMPACTION.md`,
advisory pressure indicators in `G1_CONTEXT_PRESSURE.md`, and exact profile
selection from the continued work unit in `G1_WORK_UNIT_PROFILE_ACQUISITION.md`.
