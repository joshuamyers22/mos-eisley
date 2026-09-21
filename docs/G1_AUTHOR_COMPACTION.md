# G1 visible author compaction and reconstruction

Status: implemented on 2026-09-21. This is the author-only compaction slice of
plan §§6.6.3, 6.7 and 26.4. Advisory context-pressure indicators are documented
separately in [G1_CONTEXT_PRESSURE.md](G1_CONTEXT_PRESSURE.md).

## Boundary

`ConversationController.compact_author()` accepts a strict, versioned author draft
only while all covered conversation work is settled. The local controller builds
the durable manifest; a model-supplied summary never chooses its own scope,
lineage, authority, source digests or omission accounting. The transition consumes
no recorded exchange and is committed atomically. A failed validation or save
leaves the pre-compaction state current.

Compaction is capped at three advancing revisions. Each revision binds the owner
and workspace, source-state and transcript digests, the exact contiguous message
prefix, prior-compaction digest, compactor/model/policy identities, byte reduction,
truthful token-count availability, and any checkpoint/work-unit/ledger lineage.
Repository revision is recorded when a continuation supplies one; otherwise the
manifest says it is unavailable.

## Authority and loss

Every covered non-review user message is retained verbatim in source order with
its digest, settled status and steering link. Only the newest non-cancelled
instruction is marked current; cancelled work stays cancelled and older
supersession is explicitly unknown rather than guessed. Optional objective,
constraint, decision, rationale, approval, effect, spend, unresolved-work and
artifact statements require an exact user or assistant source excerpt. These
statements and the summary are untrusted derivatives and grant no authority.
Review content cannot become author material, and the model-visible preamble says
quoted or retrieved text must not be promoted into an instruction.

Assistant answers, review content and runtime metadata are separately disclosed as
omitted categories and positions. Their originals remain in the private JSON or
SQLite transcript. Exact excerpts may be included for material provenance, but the
full answer does not enter the compacted prompt.

## Reconstruction and request admission

Every strict state validation reconstructs source bindings, exact user text,
steering ancestry, omissions, source transcript digest and byte counts from the
retained originals. Missing, edited, reordered or cross-scope inputs invalidate
the derivative. SQLite reconstruction uses semantic fields common to hot and cold
entries, so artifact archival does not change compaction identity.

The next author request uses selection policy 2: compacted prefix positions are
accounted for separately from raw selected turns and ordinary omissions. The
untrusted derivative is placed in the system context; post-boundary exchanges and
the current message remain ordinary turns. The schema-4 compaction receipt, retained
inside current schema-5/6 admission, freezes the exact compaction identity, lineage
and before/after sizes before provider dispatch.
Later compaction cannot rewrite a historical admission.

`/context` preview schema 4 identifies the reconstructed positions, compaction
digest and source/model-visible byte counts. `/context N` reports the same durable
metadata for an admitted request. Both say originals are retained and that the
derivative grants no authority.

Hard context and model-request budgets are still checked after composition. An
overflow leaves the message queued, consumes no attempt and does not fall back to
a partial summary.

## Acceptance coverage

Deterministic tests cover source-bound material, exact user text, omitted full
answers, schema-4 dispatch admission, preview visibility, mutated and missing
originals, advancing lineage, the three-revision cap, atomic save failure,
post-compaction overflow, and JSON/SQLite round trips. The installed-wheel smoke
suite imports and exercises the same public package boundary.
