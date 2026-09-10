# Session storage budgets and expansion

The default recorded preview stores each conversation in one private JSON snapshot. Its
default budget is 2 MB (2,000,000 bytes). That default suits a bounded preview;
it is not the long-term capacity target for a coding conversation.

An [opt-in SQLite backend](CONVERSATION_SQLITE.md) now provides incremental message
and artifact persistence plus metadata pages. The controls below describe the JSON
backend unless specified; SQLite shares the per-session logical budget but uses
`--limit`/`--cursor` for listing. Explicit single-session migration now previews and
copies JSON into SQLite in the same root while preserving the source; see the
[migration guide](CONVERSATION_SQLITE.md#import-an-existing-json-session).
The transcript CLI now reads bounded SQLite text pages with artifact references;
interactive transcript paging, bounded resume and bulk migration remain planned.

## Current controls

Choose a larger budget for a new session, or change a saved session's budget:

```sh
mos --session-max-bytes 8000000
mos resume --last --session-max-bytes 8000000
mos sessions
```

The supported range is 64,000–32,000,000 bytes, including the snapshot envelope,
transcript, reviews, retained recordings and historical memory. The budget is
saved with the session and displayed at startup; subsequent resumes need no repeat
flag. Existing sessions without the field retain their 2 MB budget and canonical
hash. Listing reports actual serialized bytes and the selected maximum, also as
`snapshot_bytes` and `snapshot_max_bytes` in JSON output.

A resize preserves messages, memory, recordings and consumed attempts. It saves a
new revision without dispatching work. Queued messages remain paused until explicit
continuation. A requested reduction must fit the complete resulting snapshot;
otherwise the saved selection remains unchanged and the command exits. No text is
truncated or automatically deleted. For an oversized attempted save, reopen the
last durable snapshot with a larger budget; an unsaved message or answer cannot be
recovered merely by raising the limit.

Combine `--session-max-bytes` with `resume --refresh-memory` to save the memory and
budget changes in one transition. Normal recovery may first mark a previously
running request interrupted; it never replays that request. Snapshot replacement
and directory fsync retain the existing crash rules: a failure after replacement
may leave the new file present without confirmed durability, so reopen to inspect.

Catalog scans have a separate 8 MB aggregate input budget. For a directory with
larger snapshots, explicitly increase it for listing or latest-session selection:

```sh
mos sessions --catalog-max-bytes 64000000
mos resume --last --catalog-max-bytes 64000000
```

The catalog scan maximum is 128 MB. This is a per-command work budget, not a saved
session setting. Scans still validate snapshots from other workspaces before
filtering, return no partial result after a failure, and enforce 256 candidates
and 4,096 directory entries. Resume by explicit session ID and exact-hash deletion
do not scan the catalog. Reads have an absolute 32 MB per-file ceiling before JSON
validation and additionally enforce each snapshot's saved budget after decoding.

These controls do not change the 16-message/attempt preview limits, the built-in
two-exchange recording, model request/history limits, or memory's separate 32 KiB
combined context limit. Snapshots are still read and rewritten in full. Larger
budgets increase disk use, serialization cost and peak memory; they are an interim
control, not incremental storage or a disk-space reservation. Disk-full failures
still stop work through the existing persistence-failure path.

## Planned incremental storage

The first SQLite adapter implements incremental writes, session-scoped artifact
reuse, transactional deletion and bounded metadata/transcript CLI pages. It still reconstructs
full logical state for load/save and retains the preview's message cap. The stages
below remain the complete target, including bulk migration and the long-session gate.

Implement these stages under the storage and ownership contract in
[plan §17](mos-eisley-plan.md#17-run-artifacts-and-telemetry):

1. Introduce a versioned local SQLite metadata index and incremental session
   records. Store large immutable review/tool artifacts and memory revisions in
   private, owner-scoped objects. Persist references rather than copying the same
   memory/recording into every message or rewriting the transcript each turn.
2. Commit each transition and its artifact references atomically before dispatch.
   Preserve revision checks, exclusive session ownership, consumed attempts,
   steering links and historical memory. Detect incomplete writes on recovery;
   never replay an uncertain tool effect or provider request automatically.
3. Extend the implemented metadata and transcript CLI pages into interactive
   navigation using stable cursors tied to a consistent view. Loading one page
   must not scan or decode all transcripts.
   Opening/resuming a session loads a bounded working set plus explicitly selected
   artifacts. Keep fresh-session isolation and critic isolation intact.
4. Separate disk retention, page/record read limits, active context, pending-input
   capacity and provider spending budgets. Make retention and total storage quotas
   configurable; show usage before admission fails. Keep current memory bounds
   independently configurable only through their own future policy work.
5. Add visible, versioned context compaction that retains user instructions,
   decisions, unresolved work and required steering ancestry. Preserve original
   evidence in storage and record what was selected or omitted from each request.
   A disk quota increase never authorizes sending more content to a provider.
6. Extend the implemented single-session JSON-to-SQLite import to bulk and
   cross-root migration with owner preservation, dry-run sizing, interruption
   recovery and verifiable counts/digests. Do not silently rewrite
   old snapshots when listing. Add retention previews and safe cleanup of
   unreferenced objects, including interrupted writes; explain backup/journal
   expiry instead of claiming secure erasure.

Before replacing the current backend or lifting the message cap, test at least
1,000 messages and retained content above 32 MB with measured bounded page reads.
Exercise restart at every commit boundary, disk-full and truncated writes,
concurrent writers, corrupt/missing objects, stale cursors, migration interruption,
retention racing with readers, project/user isolation and independent reviews.
These acceptance checks can use deterministic fixtures without paid provider calls.
Remote PostgreSQL/object storage follows equivalent server-side ownership and
retention enforcement; it is not part of the current local snapshot implementation.
