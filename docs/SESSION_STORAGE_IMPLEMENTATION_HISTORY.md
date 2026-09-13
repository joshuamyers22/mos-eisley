# Session storage implementation history

Archived from project plan §17.7 and the roadmap on 2026-09-13. These entries
preserve the implementation sequence, including statements that later entries
supersede. They are historical evidence descriptions, not the active work queue.
Use [plan §17.7](mos-eisley-plan.md#177-long-session-storage-and-independent-budgets)
for the current contract and [ROADMAP.md](ROADMAP.md) for delivery status.

## Project plan history

**Direction following the 2 MB capacity discussion:** the snapshot limit is an
interim preview constraint, not a long-session product target. The first
[storage-budget implementation](CONVERSATION_STORAGE.md) now lets the user save a
64 KB–32 MB snapshot budget with `--session-max-bytes` on launch or resume. The
default remains 2 MB; legacy canonical hashes remain unchanged. `mos sessions`
reports actual bytes and the saved limit. Listing/latest selection has a separate
8 MB scan budget, explicitly adjustable up to 128 MB with `--catalog-max-bytes`.
Budget changes preserve history and consumed attempts and do not dispatch work.

The default JSON backend still reads and rewrites whole snapshots. An
[opt-in SQLite adapter](CONVERSATION_SQLITE.md) now commits changed message records
and session-scoped artifact references transactionally, with exact-state deletion
and bounded metadata pages. Cursors bind the owner, database, workspace and catalog
generation; a changed catalog requires restarting pagination. SQLite currently
verifies historical entries one at a time on initial resume, then uses reference-based
working state for current records; active memory/recordings remain decoded. Its physical file has an
initial 256 MB ceiling. `mos session-migrate SESSION_ID` now previews a same-root
JSON-to-SQLite copy; applying requires its exact source hash. Import preserves
owner, revision, history and consumed attempts, verifies the reconstructed state
inside the transaction and retains the JSON source. Verified retries cover rollback
and an already committed import. Single-session cross-root transfer is described
below; retention and incomplete database initializer repair remain open.
`mos session-transcript SESSION_ID` now reads
bounded, verified text pages without loading the header or artifact contents.
Pages use saved per-entry digests and owner/session/catalog-bound cursors; older
indexes require an explicit exact-hash preparation step. The SQLite terminal now
uses this reader for F5 history browsing, Page Up/Down navigation and F6 reload.
It retains one page plus visited cursors, serializes background reads, discards
obsolete results and preserves the draft. Session changes clear the selected page;
browsing never dispatches or saves work. Its live display shows four recent messages.
F7 selects a memory/review reference on the current page; F8 opens or closes one
artifact. `mos session-artifact SELECTION` provides the same explicit read through
the CLI. Selections bind the store, owner, workspace, session, snapshot, catalog
generation, message position, field, hash and byte size. Reads verify the selected
message reference, enforce a 512,000-byte default before fetching the artifact,
then verify its hash and typed schema. The CLI accepts an explicit limit up to
32 MB; this budget covers stored payload bytes, not rendered output or RAM.
The terminal retains at most one expanded artifact and clears it on selection,
page, session or view changes; obsolete background results are discarded.
Expansion grants no model or critic access.

SQLite saves now include a derived resume checkpoint: the exact stored header hash
and byte size, plus bounded message status, review kind, steering links and record
sizes. Full loads verify it against the complete state. `mos resume --last
--storage-backend sqlite --inspect` reads this checkpoint in a read-only transaction,
verifies the header, and selects the last four messages, queued/running work and
their complete steering ancestry. It verifies only selected message payloads and
reference availability; artifacts stay unexpanded. Header plus selected records
must fit 512,000 bytes, with admission before fetching message payloads. Inspection
reports omitted-message count, pending positions and which running position would
be interrupted on normal resume. It does not recover, save or dispatch work.
Older indexes require the existing exact-hash `session-transcript --prepare` step,
which now prepares both page and resume metadata while preserving state and raw
records. The checkpoint still has a 16-message bound and needs a scalable layout
before the message cap can be lifted.

Routine SQLite saves now reuse a verified checkpoint while the same connection
observes no external commits or uncoordinated local writes. The write transaction
checks the stored index and expected revision/hash, skips unchanged message and
artifact writes, inserts new artifacts and removes only unreferenced ones. It does
not reread old payloads into Python for the full-state compatibility API; the
reference-based controller path streams retained bytes as described below.
External commits anywhere in the
database trigger full session validation before another save. Failed operations,
preparation, deletion and connection reopen clear the local checkpoint; publication
happens only after a successful commit. No artifact payload is cached in this
checkpoint, only bounded metadata, canonical verification status and artifact digests. Import and explicit
load/delete retain full validation.

Chat dispatch now builds context through a text-only message interface and admits
the canonical UTF-8 JSON for system instructions and selected turns before saving
`running` or consuming an attempt. Both backends retain an independent
`--context-max-bytes` budget (256,000 default; 4,000–1,000,000 range). Selection
preserves all earlier completed exchanges and unanswered steering ancestry;
active memory contributes through the system instructions, while historical
memory/review artifacts stay outside selection. An oversized request reports its
required size and saved limit, remains queued and pauses continuation. No automatic
compaction or omission occurs. This budget is neither provider tokens nor a bound
on complete wire requests or peak RAM; review execution retains its isolated packet
limits. The selected config is frozen before the running transition and reused for
dispatch. Context resizing preserves attempts and saves its own transition.
The complete model request also passes the agent loop's shared byte-budget check
before the running transition; a larger context budget cannot bypass the recorded
provider's 79,800-byte usable input limit. Provider-budget rejection likewise leaves
work queued, reports required/available bytes and consumes no attempt.

SQLite controllers now release historical memory/review values during incremental
initial verification and retain their admitted references. Current saves validate working
inputs and source-record hashes, stream archived bytes in 32 KiB chunks, and preserve
the canonical snapshot hash and logical byte budget without rebuilding historical
artifact objects. Changed records, artifact insertion/collection and generation
updates remain atomic; checkpoint and working-state publication follow commit.
Archived content cannot change through a reference; queued cancellation and
running-to-interrupted recovery are the admitted status-only changes. Queued review
packets hydrate at execution under a 512,000-byte aggregate record/artifact input
limit. At most the latest result stays decoded for the live renderer. JSON snapshots
reject runtime references. Older indexes and noncanonical artifact JSON retain the
full-state compatibility path until an ordinary save and reopen.

Current prepared sessions now verify cold loads and external commits one historical
entry at a time. Header/entry hashes and sizes, contiguous positions and the complete
artifact inventory are verified inside one transaction. Each entry admits its packed
record plus referenced artifacts against 512,000 bytes before fetching them, then
checks hashes, complete typed entry constraints and historical memory identity.
Decoded historical values are released before the next entry; only the latest
review result remains cached. Cross-entry progress and steering still validate,
and streamed canonical bytes must match the exact snapshot hash, logical size and
summary before publication. Legacy record whitespace/defaults preserve semantics;
unprepared indexes and noncanonical artifacts keep the full-state compatibility path.
Failed reads publish no new state/revision and clear the previous checkpoint.

Active inputs now have independent per-launch limits: `--active-memory-max-bytes`
(131,072 default, 4,096–262,144 range) and `--recording-max-bytes` (2,000,000 default,
4,096–32,000,000 range). SQLite checks both stored header inputs before fetching
either artifact, including unprepared legacy loads and external-commit revalidation.
Recording files are admitted before JSON decoding. Canonical selected memory and
recording sizes also pass admission before controller recovery, memory refresh,
transitions and dispatch. A rejected open does not recover/save/dispatch; a rejected
refresh leaves the controller usable. The welcome and structured lifecycle event
show the current limits. They are not persisted and cannot alter saved hashes,
attempts, history, memory-content bounds or provider authority. Raising storage or
context budgets does not raise these limits. Historical memory has separate bounds.
JSON still decodes its whole bounded snapshot before controller admission; local
memory files retain their existing bounded readers. These limits cover serialized
inputs, not total process RAM.

Active-input size checks and retained-recording integrity checks now stream
canonical JSON encoder segments instead of allocating a complete encoded string
and byte buffer. One fingerprint contains the exact SHA-256 and byte count; fresh
launch, controller startup and refresh reuse that checked recording digest within
the operation. There is no cache keyed by model identity: nested changes are
measured again at later boundaries, and changed recordings still fail resume or
retained-state validation. The JSON-compatible model tree and one encoder segment
remain resident; large scalar fields can produce large segments. Other state and
persistence boundaries still serialize active values, so this does not complete
bounded transitions or establish a latency improvement.

Working-state saves now encode each packed header/message record once per operation.
The admitted bytes and message digests are reused for archive checks, checkpoint
metadata and writes; new records no longer undergo an encode/parse round trip during
preparation. Selected-entry hydration likewise reuses its record encoding for
source verification and byte admission. Cold resume does not prepare the already
verified message records again when normalizing the header. Prepared records are
operation-local, with no persistent payload or model-identity cache. Existing
validation, exact snapshot hashes, record limits and atomic publication still apply.

Runtime-state revalidation now rebuilds a Python data tree and applies the strict
schema without encoding and parsing a complete state JSON buffer. Nested models
and mutable containers are revalidated and detached; tuples and UTC timestamps
retain their native types. The excluded latest-review cache also receives full
nested schema validation before its hash/summary checks and reattachment. Malformed
runtime values cannot rely on JSON conversion to coerce their types. Persisted JSON
readers keep their existing decoding boundary, including legacy defaults and date/
tuple conversion; valid runtime states preserve exact canonical bytes. The complete
working data tree still exists, and active-input integrity checks still serialize
their selected values. This reduces allocation but does not bound a transition to
only its changed fields.

SQLite working saves now preflight their exact logical snapshot size inside the
write transaction, after checkpoint and archive validation. A shared canonical
traversal counts record structure and artifact lengths, including every repeated
reference and the snapshot envelope. When the checkpoint is current, oversized
saves reject before artifact payload reads or session writes; the storage error
carries required/allowed bytes. Changed or missing checkpoints still undergo cold
verification first.
Admitted saves continue streaming every logical history byte, verifying hashes and
requiring exact agreement with the preflight size before commit/publication. This
adds a record/metadata pass to successful saves; it avoids archived payload work
on capacity rejection but does not provide bounded accepted transitions.

Admitted working saves now reuse repeated small archived artifacts within a
save-local cache capped at 64 KiB of encoded payload. Only complete, size- and
SHA-256-verified immutable chunks enter it; partial reads and late failures leave
no cached result. First eligible values that fit share their bytes across later
references. Single-use, oversized, non-fitting and newly encoded values bypass
the cache. Every occurrence still contributes its bytes to the canonical snapshot
hash and logical size. The cache clears when streaming exits and never carries
payloads into the next save or cold verification. This bounds added cached payload,
not total process RAM, and reduces repeated disk reads rather than full-history
hashing or working-state validation.

Cold verification still reads all history. Admitted active memory/recording values
remain decoded, and each save still hashes all logical history bytes. The current
working state keeps text for all 16 messages. Next reduce text/record bookkeeping
into bounded transitions and reduce repeated active-input serialization. Preserve
attempt accounting, interrupted-work recovery and
steering ancestry. The inspection selection is not a provider context policy;
context selection/compaction must explicitly preserve or account for earlier intent.
Neither backend has passed the long-session gate below.

Pending message text now has an independent per-launch budget through
`--pending-text-max-bytes` (default 64,000 UTF-8 bytes; range 4,000–512,000).
Chat, steering and review-prompt submissions count queued text before saving;
rejection reports usage without changing saved work or attempts. The composer and
TUI message editor retain rejected drafts. Typed `/steer TEXT` and `/review` now
wait for durable admission before clearing the editor, so budget/capacity or
missing-prerequisite rejections preserve the exact command. Stop and quit still
cancel pending handoffs; pasted or explicitly literal commands remain text.
Running/finished text, review artifacts
and unsent input buffers retain separate bounds. A lower limit on resume does not
block existing queued work from running or being cancelled. The setting is not
persisted, and SQLite needs no queued artifact hydration to perform admission.
This supplies the pending-text part of independent budgets, not a total RAM quota
or bounded history transitions. See the
[pending text contract](CONVERSATION_STORAGE.md#pending-text-budget).

`/context` now provides an ephemeral, versioned selection preview for the next
queued chat. Dispatch and preview share one projection function; the report maps
turns to source positions, explains omitted positions, and hashes/measures exact
canonical system-and-turns JSON with selected saved memory. It reports metadata
without copying message or memory text, saves nothing and consumes no attempt.
Queued reviews retain their isolated-packet boundary. Active work makes a preview
provisional; the TUI marks it stale after revision changes. Existing context rules
are preserved. This is visibility into current selection, not persisted dispatch
provenance, compaction or evidence that the long-session gate has passed.

The preview now also measures and fingerprints the complete canonical model request
through the same builder and budget resolution used before dispatch. Ephemeral
preview schema 2 adds route, request bytes/hash, usable input limit, output reserve,
headroom and an independent fit result. Selection policy remains version 1.
A context may fit the saved context budget while the complete request is too large;
both results remain visible without consuming an attempt. These are local byte
budgets, not native provider payload/token estimates. Actual dispatch still
revalidates all limits, current memory and recording availability.

New recorded chat attempts now persist a version-1 request admission on the message
in the same save as the running status and consumed exchange, before model-client
dispatch. It records the source revision and message count, exchange index,
versioned source selection/omissions, context fingerprint/limit, selected-memory
flag and complete request fingerprint/budgets. Outcomes and crash recovery retain
it unchanged; later queue, memory and limit changes do not rewrite historical
admission. It contains no copied input text. SQLite keeps the metadata inline in
bounded records for transcript and resume inspection without artifact expansion;
both backends and migration preserve it. Existing entries remain unmodified with
no invented historical provenance. This records admitted inputs and may survive a
crash before transmission; it is not proof of provider receipt. Visible compaction,
retention and the long-session capacity gate remain open. See the
[saved admission contract](CONVERSATION_STORAGE.md#saved-request-admissions).

`/context N` now inspects that saved metadata directly from a zero-based transcript
position in the line and screen terminals. It shows the original hashes, byte
budgets and source selection with the current message status, without rebuilding
requests, loading historical artifacts, saving or enabling paused work. Missing,
queued, review and legacy targets yield notices without reconstructing admission.
The version-1 inspection event is separate from the schema-2 next-queued preview.
The screen toggles the selected report and marks the displayed status/revision
stale after session changes; refreshing leaves the admission unchanged. Pasted and
composed command text remains literal input.

Bounded same-root JSON-to-SQLite batch migration is now available through
`session-migrate-batch`: 1–32 explicit session IDs, at most 64 MB of selected source
JSON, metadata-only planning and an exact batch hash required for apply. The plan
binds source hashes/sizes, owner, workspace and storage-directory identity while
excluding destination status, so a partial batch can retry the same selection.
Every source is preflighted before destination work, then each import uses the
existing source lock, size/hash rechecks, full destination verification and atomic
transaction. Completed imports remain after a later failure; results report the
verified prefix and failing session. Retry verifies existing copies and does not
overwrite advanced destinations. Read-only preview refuses hot journals; explicit
apply permits recovery after validating the batch selection. Sources, attempts and
admission records are preserved. Retention and the
long-session capacity gate remain open. See the
[batch contract](CONVERSATION_SQLITE.md#import-a-selected-batch-of-json-sessions).

Single-session cross-root JSON-to-SQLite copies are now available through
`session-transfer`. Its read-only metadata preview binds both existing private
directory paths/device/inodes, owner, workspace and source hashes/sizes; apply
requires the exact transfer hash. The source lock is held throughout, the
destination uses its own session lock, and directory identity is checked before
destination metadata creation. Source selection and both directories are checked
again inside the atomic import transaction. Identical existing copies verify on
retry, including after a lost commit acknowledgment; advanced destinations are
never overwritten. Transfer retains JSON, original workspace, memory, evidence,
admission records and attempts, without recovering running messages or starting
queued work. Read-only preview refuses hot journals; explicit apply permits
recovery after selection validation. Physical
retention and the long-session gate remain open. See the
[transfer contract](CONVERSATION_SQLITE.md#copy-a-json-session-to-another-storage-directory).

Bounded cross-root batches are now available through `session-transfer-batch`:
1–32 explicit session IDs and at most 64 MB of selected source JSON, with all
sources preflighted before destination inspection. The version-1 batch transfer
plan binds both directories, owner, workspace and exact source metadata; apply
requires its hash. Each single-session transfer is bound to that selection and
limits source rereads to the selected size. Imports commit independently under
both session locks; a later failure reports the verified prefix and failing ID
without undoing earlier commits. Retry verifies existing copies, including a
copy committed before its acknowledgment was lost. Directory replacements,
source changes and advanced destinations cannot silently change the selection.
Preview remains read-only and explicit apply permits hot-journal recovery.
Source files, workspace identity, evidence, admission records and attempts are
preserved. Retention and the long-session capacity gate remain
open. See the [batch transfer contract](CONVERSATION_SQLITE.md#copy-a-selected-batch-to-another-storage-directory).

Single-session reverse migration is now available as `session-export`, copying
SQLite into JSON in another existing private directory. The metadata-only preview
binds both roots, backend direction, owner/workspace, exact state hash, revision,
message count and canonical output size. Apply requires its export hash, holds
both session locks, writes and syncs a private temporary snapshot, then rechecks
source state, directory identity and destination absence before atomic publication.
Identical copies verify on retry; different or invalid destinations are rejected.
The original revision, attempts, admission records, memory and evidence survive
SQLite-to-JSON-to-SQLite round trips. Queued/running entries are not resumed.
SQLite remains read-only even on apply, so hot source journals block export and
must be recovered separately. Output retains the saved logical/32 MB limits;
complete state is decoded. Pre-publication crashes can leave private temporary
files; retry publishes a complete snapshot and post-publication retry verifies
the existing copy. Retention and the long-session gate
remain open. See the [export contract](CONVERSATION_SQLITE.md#export-a-sqlite-session-to-json).

Same-directory export is now supported and is the `session-export` CLI default
when `--destination-storage` is omitted. SQLite and JSON share one session lock
in that directory, so export reuses the held lock and directory handle for JSON
inspection/publication while SQLite remains read-only. Different paths to the
same physical directory use the same lock behavior. Plans for this layout use
version 2; cross-directory version-1 plans and hashes remain unchanged. Both
paths and identities are still bound to the export hash, and version/layout
mismatches are rejected. Existing JSON copies are verified if identical and
rejected if different, preserving originals retained by earlier migrations.
Explicit JSON resume can advance that copy without modifying SQLite; a later
export rejects the divergence. Retention and the long-session
capacity gate remain open.

Bounded SQLite-to-JSON batch export is now available through
`session-export-batch`, selecting 1–32 explicit IDs and at most 64 MB of canonical
JSON output. The version-1 batch plan binds sorted single-export plans, both
directories, owner/workspace and exact source state/size metadata; apply requires
its hash. Preflight verifies every source before destination JSON work and retains
only metadata between sessions. Indexed snapshot sizes gate full decoding against
the remaining output budget; full verification checks those index claims. Each
execution read and final source recheck is capped at the selected snapshot size.
Publication remains per session under the existing locks, with a verified prefix
and failing ID reported after a late failure. Retry verifies identical published
copies, including a publication whose acknowledgment was lost, without overwriting
different destinations. Both directory layouts preserve SQLite, evidence and
attempts, refuse hot source journals, and leave execution paused. This admits
verified output bytes rather than reserving disk or bounding total Python memory.
Retention and the long-session capacity gate remain open. See the
[batch export contract](CONVERSATION_SQLITE.md#export-a-selected-batch-of-sqlite-sessions).

The first retention step now provides `session-cleanup SESSION_ID`: explicit
storage-owner selection of unpublished JSON staging files, including interrupted
first writes without a published session or readable workspace metadata. A
version-1 plan binds directory/lock/file identities, timestamps, sizes and streamed
content hashes; apply requires its exact hash and validates all targets under the
shared session lock before removing any. The bounded pass admits 256 files,
32 MB per file and 64 MB total within a 4,096-entry directory scan. Partial removals
and directory-sync failures produce receipts; restart requires a fresh preview of
the remaining files, including an empty selection when a sync needs retrying.
Published JSON, SQLite, journals, backups and lock inodes are preserved. Temporary
bytes are discarded rather than recovered. The command is explicitly storage
scoped because truncated bytes cannot prove project membership. Broader object
retention, quotas, backup/journal expiry and the capacity gate remain open. See the
[cleanup contract](CONVERSATION_CLEANUP.md).

Workspace retention preview is now available through `session-retention`, using
an explicit UTC saved-time cutoff and a configurable keep-newest count (default
20). One read-only SQLite transaction admits at most 1,000 workspace indexes,
checks their digests and identity, and reports candidates, retained sessions, all
retention reasons and indexed logical-byte totals. Newest, active and noncompleted
sessions are protected. Metadata is read one bounded index at a time without
hydrating bodies; activity probes are momentary and do not reserve deletion. The
version-1 plan binds storage, workspace, store/generation, policy and ordered
results. Its hash identifies the observation and grants no deletion authority.
The report remains metadata-only and has no apply option. See the
[retention preview contract](CONVERSATION_RETENTION.md).

Single-session retention apply is now available through `session-prune`. An
explicit ID must qualify under the cutoff/keep-newest policy and pass full-state
verification. Its separate version-1 plan binds the complete retention observation,
selected state digest, database/session-lock identities and artifact counts. Apply
requires that prune hash, repeats read-only preflight before writable access, and
rechecks policy and full state under `BEGIN IMMEDIATE` before atomically deleting
the session and its cascading records. Root and file identities are rechecked;
generation or observed policy changes require a fresh preview. Receipts are issued
after commit, and missing IDs are not treated as proof of an earlier successful
prune. JSON copies, temporary files and lock inodes remain. Automatic policy
apply and physical-space reclamation remain open. See the
[pruning contract](CONVERSATION_PRUNE.md).

Explicit batch retention apply now uses `session-prune-batch` for 1–32 unique IDs
and at most 64 MB of logical snapshots. All selected session locks are held in
sorted order. Each verification phase reads the workspace policy once, rejects
ineligible or oversized selections before loading bodies, and fully verifies each
selected state while releasing previous states. The separate batch hash binds one
retention observation and all selected state/file identities. Apply repeats
read-only preflight before writable access, then rechecks the complete selection
under `BEGIN IMMEDIATE`. All selected rows and cascades are deleted in one commit
with one generation increment; precommit failures roll back the entire batch.
Missing IDs are not proof of a successful prior batch, and JSON copies remain.
Automatic expiry, quotas and physical reclamation remain open. See the
[batch pruning contract](CONVERSATION_BATCH_PRUNE.md).

## Roadmap history

   [Snapshot budgets](CONVERSATION_STORAGE.md) are now configurable per session,
   with visible usage and a separate bounded catalog scan override. The 2 MB default
   remains an interim preview limit. Plan §17.7 now sequences incremental records,
   paginated listing/transcript reads, independent context/retention budgets,
   explicit migration and recovery tests before lifting the message cap.
   The first [SQLite adapter](CONVERSATION_SQLITE.md) now implements opt-in
   incremental message/artifact writes, atomic saves/deletes and bounded metadata
   pages with generation-bound cursors. Explicit same-root JSON-to-SQLite migration
   now preserves exact state and source files, with dry-run sizing and verified
   retries after transaction interruption. Bounded same-root batches now select up
   to 32 explicit sessions under a 64 MB source budget, bind the selection to a
   versioned batch hash and commit one import at a time. Partial results and retries
   verify completed copies without overwriting or recovering uncertain attempts.
   Single-session and bounded batch cross-root copies now bind both directories
   and source selections to preview hashes, with per-session transactions and
   verified retries. Single-session `session-export` now copies SQLite back to JSON
   in the same or another private directory with exact-hash preview, atomic
   publication and source preservation. Same-directory export reuses the shared
   session lock and version-2 plans; existing cross-directory hashes retain version 1.
   Bounded batch export now preflights up to 32 sessions and 64 MB of JSON output,
   binds exact source plans to one hash, and reports verified per-session results
   for safe retry after partial publication. Bulk retention remains open. The transcript CLI now
   reads bounded text pages using saved entry hashes and stale-cursor guards, with
   explicit preparation for legacy indexes. SQLite's terminal now browses those pages with
   F5, Page Up/Down and F6 reload, retaining one page and preserving the draft.
   F7/F8 and `session-artifact` now expand one explicitly selected memory/review
   artifact with snapshot binding, integrity checks and a separate byte budget.
   A separately verified resume checkpoint now supports `resume --inspect` with
   the last four messages, all queued/running work and required steering ancestors,
   under a fixed record-read budget. It leaves artifacts unexpanded and performs
   no recovery. Routine saves reuse a verified checkpoint and skip unchanged writes.
   SQLite controllers now retain historical artifact references and stream stored
   bytes when saving, preserving canonical hashes without rebuilding old artifact
   values. Queued reviews hydrate one admitted packet at execution; at most the
   latest result stays decoded for the renderer. Initial loads and external commits
   now verify historical entries one at a time under a separate input bound, then
   stream the exact snapshot hash and logical size. Active memory/recording values
   remain decoded. Chat context uses a text-only selection
   interface and a separately saved byte budget, checked before an attempt is
   consumed. It preserves completed history and steering, and pauses oversized
   queued work with required/available byte counts. Per-launch memory/recording limits
   now admit SQLite header sizes before either artifact is fetched, including legacy
   loads, and bound recording-file reads. Controller recovery, refresh and dispatch
   check canonical selected inputs; limits leave saved hashes unchanged. Size/hash
   checks now stream canonical JSON and reuse the recording fingerprint within an
   operation; nested mutations are checked anew at the next boundary. Working saves
   now encode each packed record once and reuse its bytes/digest for admission and
   persistence; cold resume skips redundant preparation of verified entries. Runtime
   revalidation now checks a fresh native data tree without a whole-state JSON
   buffer, including full schema validation of the excluded review cache. Working
   saves now preflight exact logical size from record structure and artifact lengths;
   a current checkpoint permits capacity rejection before artifact reads or writes.
   Admitted saves still stream all logical history and verify the preflight size.
   Repeated small archived artifacts can now reuse verified chunks within a 64 KiB
   cache for that save, reducing repeated disk reads without carrying payloads
   between operations. Queued message text now has a per-launch UTF-8 byte budget
   checked before saving new chat, steering or review-prompt submissions. Rejection
   preserves queued work, attempts and message drafts; tighter resume limits allow
   existing work to run or be cancelled. Typed `/steer` and `/review` submissions
   now retain editor text until durable admission, including rejection for missing
   prerequisites, while stop/quit still cancel pending handoffs. `/context` now
   previews selected turn sources, steering ancestry, omissions and canonical
   context usage through the same projection as dispatch, without saving or
   starting work. This metadata preview is versioned and ephemeral. Preview schema
   2 now includes complete request bytes/hash, route, output reserve, headroom and
   the independent request fit result through the same builder used by dispatch.
   A saved-context fit does not imply the complete request fits. New chat attempts
   now atomically retain versioned admission metadata with the running transition:
   exact context/request fingerprints, limits and selected/omitted message positions.
   Completion, failure and recovery preserve it; existing entries are not backfilled.
   SQLite transcript/inspection reads expose this metadata without artifact hydration.
   `/context N` now exposes a saved message's admission in both terminal modes,
   showing historical hashes, budgets and selections with its current status.
   It reads existing metadata without rebuilding requests, saving or enabling work;
   missing/legacy admissions produce notices and the TUI marks changed views stale.
   Admission does not prove provider receipt. Visible compaction, smaller
   text/record transitions and the long-session acceptance gate
   remain open.
   Single-session cross-root JSON-to-SQLite transfer now previews both directory
   identities and source sizes/hashes, then requires its transfer hash for apply.
   It retains source/workspace identity, admission records and attempts; retries
   verify existing copies without overwriting advanced destinations. Reverse
   migration and retention remain open.
   Mid-request interruption and live review
   remain open.
