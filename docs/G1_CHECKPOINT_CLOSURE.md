# G1 checkpoint closure

## Status

Implemented on 2026-09-20 as the second G1 runtime slice in plan §26.4. The
conversation controller can now close a completed milestone, material objective
change, or deliberate handoff into one private, owner/project/workspace-scoped task
checkpoint and retain a text-free receipt in the conversation state.

This slice follows the repository structure and verification practices in the local
`production-project-template`: strict versioned records, injected runtime
dependencies, compare-and-swap mutation, private durable storage, fail-closed
boundary checks and repository-wide verification.

## Closure boundary

Trusted composition injects a `TaskCheckpointStore` bound to one exact
`OwnerProjectScope` and checkpoint ID. `ConversationController.close_milestone`
refuses closure while conversation work is running, revalidates the complete G0
`TaskStateBundle`, checks exact task scope and compares the caller's expected
checkpoint revision with the conversation's saved receipt before invoking storage.

The closure reason is explicit. `completed_milestone` requires the current work
unit to be completed and its outcome to appear in the checkpoint. A
`material_objective_change` or `deliberate_handoff` requires active work, so a
queued unit cannot be represented as progress. The store also requires checkpoint
and bundle revisions to advance together, exact previous hashes after the initial
revision, and a real durable checkpoint change. A retry of the identical bundle and
reason is idempotent; stale or conflicting attempts fail without moving the head.

## Private atomic storage

One nonblocking owner-held lock serializes writers. Each fully validated task-state
bundle and its referenced evidence are saved through the existing private,
content-addressed G0 archive. A small canonical `current.json` head identifies the
checkpoint and bundle digests, their common revision, the closure reason and the
exact scope. Publishing that head uses a private temporary file, file and directory
sync, and atomic replacement.

Every read rechecks file ownership and mode, canonical encoding, scope, archive
integrity and the head-to-bundle digest/revision relationship. The bounded
checkpoint view has a configurable byte admission limit with explicit overflow;
the underlying G0 contract retains ordered next actions, the full outstanding-work
set, disclosed omissions, current verification bindings and cumulative ledgers.
Checkpoint data is not exported to the repository.

## Conversation and memory separation

After durable closure, the controller checks the returned receipt against the exact
input bundle and saves only that text-free receipt in conversation state. If the
conversation save fails after publication, the controller becomes unusable and
reports that the link is uncertain; reopening and retrying the same closure safely
repairs it. Snapshot resume preserves the receipt.

The checkpoint is not reusable memory, SQLite resume metadata, or ambient model
context. Ordinary request admission continues to classify
`checkpoint_selected=false`, and the checkpoint view is not inserted into later
prompts. Only the explicit selection and claim path described in
[G1 fresh-context continuation](G1_FRESH_CONTEXT_CONTINUATION.md) may admit its
bounded view.

## Completed G1 connections

Checkpoint closure, explicit continuation, work-unit-owned profile acquisition,
author compaction/reconstruction and advisory context pressure are connected. The
continuation path preserves aggregate ledger and lineage baselines, rejects
unresolved uncertain effects, and rechecks repository/test freshness and owned
profile material before every dispatch.
