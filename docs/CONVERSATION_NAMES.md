# Session names and resume picker

Give a conversation a memorable label when starting it:

```sh
mos chat --name "Parser cleanup"
mos --name "Boundary example" -- "Remember that the fixture boundary is ten."
mos resume --name "Parser cleanup"
```

Inside a session, `/rename Parser cleanup` changes its name and `/rename --clear`
removes it. Stop active work first. Renaming saves metadata and pauses queued work;
F4, `/continue`, or a new message explicitly continues it. Session names appear in
the header, `mos sessions`, and the resume picker. A new chat always starts fresh,
even when another conversation has the same name.

Names contain 1–120 printable Unicode characters on one line. Input is normalized
to NFC and outer spaces are removed; interior spaces remain unchanged. Controls,
newlines and bidirectional formatting characters are rejected. Lookup normalizes
and case-folds names: `Café` matches `CAFÉ`, and `Straße` matches `STRASSE`.
The immutable session ID remains the identity through every rename.

## Choose a saved session

Run `mos resume` with terminal input/output to open the picker. It lists saved
sessions for the current user and canonical workspace in the selected storage
location and backend. Use `-C PATH`, `--storage PATH`, and
`--storage-backend sqlite` to change that selection. JSON snapshot storage remains
the default; the picker does not combine backends or workspaces.

| Control | Action |
| --- | --- |
| Up/Down | Move the selection. |
| PageUp/PageDown | Move by 20 rows. |
| Type | Filter by a substring of the name or session ID. |
| Backspace / Ctrl-U | Edit / clear the filter. |
| F5 | Refresh the catalog. |
| Enter | Select the highlighted available session. |
| Escape / Ctrl-C / Ctrl-D | Cancel without opening a session. |

Rows show a compact name, full ID, saved UTC time, message/queue counts and active
status. The selected-session panel shows its full name and ID. Transcript text is
not displayed in the picker. Active sessions cannot be selected; a failed refresh
disables selection until a successful refresh. Missing storage is an error and
does not create a directory. An empty existing catalog can be refreshed or closed.

`mos resume --name NAME` uses an exact normalized name match. A unique match opens
directly. Duplicate names are allowed: terminal users choose explicitly in the
filtered picker; pipes, `--json`, `--plain`, and `--inspect` reject ambiguity with
guidance to list sessions and use an ID. Bare resume requires a terminal; explicit
IDs and `--last` remain available for scripts. Opening any selected session leaves
saved queued work paused.

Selection captures the storage directory identity and state hash. Resume acquires
the existing session lock and verifies the selection before constructing the
controller. Deleted, replaced, busy or changed selections fail; retry with a fresh
selection. It never falls back to a different session. JSON catalog reads retain
their existing non-atomic cross-session semantics; the selected state is rechecked.

## Rename a closed session

Read the exact `session_id` and `snapshot_sha256` from `mos sessions --json`, then:

```sh
mos session-rename SESSION_ID --name "Parser cleanup" --expected-sha256 SNAPSHOT_SHA256
mos session-rename SESSION_ID --clear --expected-sha256 CURRENT_SNAPSHOT_SHA256
```

Repeat the workspace, storage and backend options used by that session. The command
requires the matching owner/workspace, exclusive session lock and current state
hash. An interrupted running entry must first be resumed and stopped. A rename
increments the state revision and changes its hash and saved time, which can affect
`--last` and retention ordering. A no-op name change does not save a new revision.
Conversation content, ID and consumed recording position remain unchanged.

## Persistence and limits

The optional `session_name` field belongs to the existing versioned state and
summary contracts. It is covered by snapshot hashes and SQLite integrity checks.
Unnamed state omits the field, preserving the canonical bytes and hashes of older
unnamed sessions. Names survive restart, JSON/SQLite migration, transfer and
export. Older application versions may reject the added field in named sessions;
use the updated CLI to read them.

Names are private user-authored metadata, never model instructions or memory.
They share the existing private directory/file permissions and state byte budget.
Rename uses the ordinary store save/recovery path; SQLite may perform its normal
journal recovery when opened for writing. A failed save is not reported as a
successful rename.

The picker renders up to 20 rows at a time and retains bounded summaries for local
filtering. SQLite catalogs are read in generation-bound pages of 100, up to 1,000
sessions; these reads use the metadata index, without hydrating transcripts. JSON
uses the existing bounded full-snapshot scan: at most 256 sessions and 8 MB by
default, adjustable with `--catalog-max-bytes`. Exceeding a catalog limit fails;
use an explicit ID. Larger SQLite catalogs can still be navigated through
`mos sessions --storage-backend sqlite --limit 100` and its cursor, then resumed by
ID. This does not expand conversation capacity or connect live providers.
