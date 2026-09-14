# G1 validated author compaction

Validated author compaction is an explicit, author-only replacement for completed
chat history. It is a lossy derivative, never a new instruction or execution
authority. Critic and judge/review contexts remain isolated and are ineligible.

## Explicit two-phase boundary

1. Prepare a bounded JSON draft outside the running request. The draft names the
   exact conversation revision and message count, the previous compaction digest,
   user-message positions to retain verbatim, sourced semantic summary items,
   artifact references, complete omission ranges, relevant repository files and
   compactor/model/policy identity.
2. With work stopped and an author message queued, run `/compact FILE`. The
   controller reconstructs trusted values from saved state, inspects Git and named
   files, validates the draft, admits the resulting context against both hard byte
   limits, repeats the inspection to close the save race, and atomically saves the
   result. Queued work stays paused until `/continue`.

The file is read as one regular, non-symlink file under 128 KiB. Duplicate JSON
keys, unknown fields, malformed UTF-8 and unsafe relevant-file paths fail closed.
No compaction is automatic.

## Required draft shape

The strict version-1 object has these fields:

- `expected_source_revision`, `expected_message_count`, and optional
  `expected_previous_sha256`;
- ordered `retained_user_positions`;
- `summary.items`, each with `category`, `text`, `source_role`, ordered
  `source_positions`, `status`, optional `superseded_by_position`, and literal
  `grants_authority: false` when present;
- optional `summary.artifacts`, each with a stable ID/path, digest, availability,
  source positions, and no authority;
- ordered, disjoint `omissions` with inclusive start/end message positions,
  category and reason;
- optional unique `relevant_files`; and
- `compactor`, `model`, and `policy_version: 1`.

Summary categories are objective, constraint, decision, approval,
irreversible effect, spend, unresolved question and current work. At least one
active objective and current-work item are required. Every summary/artifact source
must exist in completed author history. An artifact claimed available must match the
live bounded relevant-file inspection.

## Preservation and authority rules

The newest completed user message and any retained steering ancestry are copied
byte-for-byte into a user turn. The currently queued user message remains unchanged.
The structured summary is rendered only as an assistant turn headed by an explicit
untrusted-derivative marker. It cannot supersede retained user text or promote text
retrieved from an answer, tool result or artifact into user authority.

Omission ranges must exactly cover every completed source position not retained.
The saved private source artifact contains the exact pre-compaction turns and source
messages, making reconstruction possible without trusting the derivative. Its
manifest binds source and derivative digests, prior lineage, retained positions,
omissions, before/after canonical bytes, labeled local token estimates,
compactor/model/policy identity and the complete Git/file inspection. The bound
private source also records the memory, task-profile and task-state input digests.

## Admission, freshness and recovery

A compaction must reduce canonical history bytes. The full prospective request must
also fit the saved context limit and the provider request limit before anything is
saved. Failure leaves the prior revision, queue and recorded-attempt count unchanged.
The controller permits at most three compactions and requires new completed author
history between them.

Before a compacted author request dispatches—and before terminal `/context` or
`/status` previews—the repository and referenced files are inspected again. Any
branch, revision, tree, dirty-state, changed-path, availability, size or digest
change invalidates the derivative. The user must validate a new compaction or start
a fresh session. Review dispatch never consumes compacted author context.

SQLite stores the whole compaction chain as a private content-addressed header
artifact; JSON snapshots retain the same strict object. State reconstruction checks
scope, session, source messages, source revision, increasing boundaries, manifest
digests and prior-compaction links. The content-free `conversation.compacted` event
reports only revision, digest, count and before/after byte totals.

## Acceptance boundary

Fixtures cover exact reconstruction and retained user text, untrusted authority,
omission/source validation, stale drafts, manifest tampering, repository changes,
hard overflow rollback, pressure counting, request selection and private persistence.
This establishes the G1 safety mechanism, not a claim that a particular summary is
high quality or that compaction improves task outcomes. Those claims remain behind
the G3 held-out evaluation gate.
