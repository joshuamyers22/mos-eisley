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
The transcript CLI and SQLite terminal's F5 browser now read bounded text pages with
artifact references. F7/F8 and `session-artifact` explicitly expand one selected
artifact under a separate 512,000-byte default read budget; the CLI can raise this
up to 32 MB without changing session retention or model context limits.
`resume --inspect` now reads a candidate working set from a separately verified
checkpoint without resuming the controller. Bounded controller resume and bulk
migration remain planned.

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

## Independent chat context budget

Both backends save a separate chat context limit. It defaults to 256,000 bytes;
`--context-max-bytes` accepts 4,000–1,000,000 bytes on launch or resume:

```sh
mos --context-max-bytes 128000
mos resume --last --context-max-bytes 512000
```

Startup displays the saved budget. Each chat request counts the canonical UTF-8
JSON object containing its `system` and `turns`, including roles, text blocks, JSON
escaping and active memory instructions. This is a content byte budget, not a
provider token limit, complete wire-request size, or peak RAM bound. Provider
request/spending limits and the separate 32 KiB memory limit still apply.
The current recorded provider admits at most 79,800 bytes for the complete
serialized model request after its output reserve and headroom. The controller
checks this independently with the same budget check used by the agent loop,
also before consuming an attempt. Its rejection reports that limit and keeps the
message queued. Raising the saved context limit cannot raise the provider limit.

Selection preserves every earlier completed exchange, the current prompt and
unanswered steering ancestry. It uses only message text/status/links; historical
memory and review artifacts do not enter that selection. Active memory contributes
through the system instructions; a completed review contributes its existing text
summary. No automatic truncation or compaction occurs. Explicit review execution
continues to use its isolated packet and existing review limits.

Both admission checks happen before persisting `running` or consuming an attempt.
Rejection reports required bytes and the saved limit, leaves the message queued,
and pauses continuation in both terminal modes. Resume with a sufficient context
budget and explicitly continue, or start a fresh session. Changing the storage
budget cannot bypass context admission. Context resizing saves a revision without
dispatch; it can also lower the limit below pending context, which then stays
queued until it can be admitted. When combined with memory/storage changes, the
context resize is a separate saved transition. Legacy sessions omit the optional
field and preserve their canonical hashes until a transition is saved.

SQLite now releases historical artifact values after initial verification and uses
[reference-based working state](CONVERSATION_SQLITE.md#controller-working-state).
Initial load still reconstructs full state. Context admission alone does not
complete bounded cold resume or the long-session acceptance gate.

## Planned incremental storage

The first SQLite adapter implements incremental writes, session-scoped artifact
reuse, transactional deletion and bounded metadata/transcript pages, including
SQLite terminal history navigation, selected artifact expansion and bounded resume
inspection. Verified checkpoints skip unchanged message/artifact writes. Current
SQLite controllers retain references to historical artifacts and stream their bytes
when computing snapshot hashes, without rebuilding their decoded values. Initial
resume and external-commit revalidation still reconstruct complete state. JSON and
legacy compatibility saves still serialize full proposed state. The preview's
message cap remains. The stages
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
3. Build on the implemented metadata/transcript CLI pages and terminal history
   browser and selected artifact reader, using stable cursors tied to a consistent
   view. Loading one page
   must not scan or decode all transcripts.
   The implemented resume checkpoint/inspection selects four recent messages,
   queued/running work and complete steering ancestry without expanding artifacts.
   Routine saves now reuse a same-connection verified checkpoint, with full
   revalidation after external commits. The controller now separates historical
   artifact values from its reference-based working state; saves stream retained
   bytes, and queued reviews hydrate one admitted packet at dispatch. Next reduce
   text/record bookkeeping into bounded transitions and bound cold loading plus
   active memory/recording hydration.
   Actual resume must load a bounded working set plus selected artifacts while
   preserving consumed attempts, recovery and isolation. The inspection selection
   is not yet a model-context policy and must not silently omit earlier intent.
4. Separate disk retention, page/record read limits, active context, pending-input
   capacity and provider spending budgets. Make retention and total storage quotas
   configurable; show usage before admission fails. Keep current memory bounds
   independently configurable only through their own future policy work.
   Chat context now has an independent saved byte budget and pre-dispatch admission,
   with complete text history and steering preserved. Artifact hydration and
   retention quotas remain separate work.
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
