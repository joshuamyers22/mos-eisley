# Reviewed selective forgetting

Remove one explicitly identified text span from current user or project memory:

```text
/memory forget project Prefer the old test runner.
```

These directly entered phrases create the same preview:

```text
forget this for this project: Prefer the old test runner.
forget this everywhere: Prefer long answers.
```

The project scope uses the session's retained memory identity, including a selected
root or mapping. The user scope applies across projects. `forget this: TEXT` asks
for a scope; missing text asks for a complete request. Mos never infers what "this"
means from previous messages, or searches other scopes for a match.

## Review and apply

The preview identifies the scope and path, text to remove, complete resulting
text, and a SHA-256 confirmation token. JSON additionally contains the full before
snapshot and character offsets. Preview reads existing memory without writing or
creating a store. No model turn is created and queued work stays paused.

After reviewing the result, copy the hash into:

```text
/memory apply-forget PREVIEW_SHA256
```

Or discard the preview:

```text
/memory discard-forget
```

An apply removes only the reviewed span, advances the saved document revision and
preserves its enabled/disabled state. It retains an empty revision marker when the
whole text is removed. The receipt reports removed text and the saved revision/hash.
A wrong hash cannot apply the pending review. Apply checks the reviewed document's
hash under the existing exclusive memory lock; concurrent edits, clearing or
changes to enabled state reject stale writes instead of overwriting them.

Each terminal session holds at most one forget or [replacement](CONVERSATION_MEMORY_REPLACE.md)
preview, in memory only. A new `/memory forget` or `/memory replace` command discards
the previous review of either kind, including when inspection or matching fails. Valid
ordinary memory write commands invalidate it before storage access, including
failed writes; `/memory show SCOPE` retains it. A discarded or replaced review
cannot be reused, even when the document is unchanged. Exiting, resuming or switching
directories starts without a pending review. Obtain a new preview in that session.

Stop or finish active work before previewing, applying or discarding. A preview
or apply does not alter active session memory, historical context or consumed
recordings. After a successful apply, use:

```text
/memory refresh
/continue
```

Refresh can independently reject context/storage limits or require a replacement
custom recording. The saved edit still exists. Memory loading stays off until
explicitly refreshed, and a disabled document stays disabled.

## Exact matching and limits

The supplied text must occur exactly once, including overlapping occurrences.
Missing text or multiple matches reject the preview; supply a longer unique span.
Matching is case-sensitive and performs no Unicode normalization, Markdown parsing,
paragraph inference or whitespace cleanup. Every character outside the chosen span
is preserved, including surrounding blank lines. A match can be part of a line;
always review the complete resulting text before applying it.

Commands require explicit nonempty text on one line within the terminal's
8,000-character limit. Existing 32-KiB memory text and private-file limits apply.
The preview is bound to a fresh per-review identifier, scope, store path, retained
workspace, before snapshot, exact span and resulting text. The store retains its
existing local integrity model; hostile same-user rollback or parent-directory
replacement remains outside that model. No new durable inode identity is claimed.

Only directly entered terminal requests create or apply reviews. Full-screen
pasted text, composed drafts, initial command-line prompts and model/tool output
cannot invoke this path. In plain/JSON mode each input line is direct user input;
use `/compose` to submit matching text literally. Rejected full-screen phrase
submissions remain in the editor for correction.

## Interrupted writes and historical copies

A write error may occur after atomic publication. A matching apply attempt consumes
its pending review before storage access, so it cannot blindly replay after a
partial failure. Inspect current saved memory and obtain a new preview. The error
explains possible publication and does not promise rollback. A stale or unsafe
current document is never replaced through the reviewed apply.

Forgetting changes the current saved document only. It does not erase older saved
sessions, previous provider requests, backups, filesystem journals, or copies of
receipts. Earlier conversation messages may still mention removed information.
Use existing session/artifact controls to manage historical copies. General
natural-language interpretation and automatic memory extraction remain planned.
