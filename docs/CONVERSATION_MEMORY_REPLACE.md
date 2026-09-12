# Reviewed memory replacement

Edit one explicitly selected span in saved user or project memory:

```text
/memory replace project {"old":"Use the old runner.","new":"Use pytest."}
```

The preview shows the target scope/path, old and new text, complete resulting
document and confirmation hash. Nothing is saved until you review it and enter:

```text
/memory apply-replace PREVIEW_SHA256
```

Cancel with `/memory discard-replace`. The user scope applies across projects;
project scope uses the session's retained root or mapping. These commands are
available in both full-screen and plain/JSON terminals. No model turn is created,
and queued work stays paused. Stop active work before editing.

## Exact text and bounds

Supply a JSON object with exactly `old` and `new`, both distinct nonempty strings.
Duplicate keys, unknown fields and invalid UTF-8 strings reject the request.
Use JSON escapes for quotes, backslashes and newlines:

```text
/memory replace user {"old":"First line\nSecond line","new":"One \"quoted\" line"}
```

The command itself must fit on one line within 8,000 characters. The complete
result must fit the existing 32-KiB UTF-8 document limit before a preview is issued.
Use selective forgetting for deletion. The old text must occur exactly once;
missing, repeated or overlapping matches reject. Matching is case-sensitive with
no Unicode normalization, Markdown parsing or whitespace cleanup. Every character
outside the span is preserved. Shell syntax in JSON strings is literal text.

## Review lifetime and storage protections

Forget, replacement and [assistant proposals](CONVERSATION_MEMORY_PROPOSALS.md)
share one active review per terminal session. A new scoped
preview command invalidates the previous review of either kind, even if the new
request fails. Valid ordinary memory writes invalidate reviews before attempting
storage access; inspection retains them. Apply and discard use their matching
operation names. Wrong hashes cannot apply. Exiting, resuming and switching
directories require a fresh preview; reviews are not persisted in session storage.

The hash binds the operation, fresh review identifier, old/new text, full before
snapshot, result and target identity. Apply verifies the current document hash
under the existing exclusive lock, rejecting concurrent edits, clearing or enabled
state changes. It preserves the enabled state and advances the revision. Unsafe
or corrupt current files cannot be overwritten through this command. The existing
local integrity model trusts the same user and parent directories; hostile owner
rollback is outside that model.

A matching apply consumes the review before storage access. If a write fails after
atomic publication, the edit may already exist. Inspect saved memory and create a
fresh review; the error does not promise rollback or allow automatic replay.

Only directly entered controls invoke edits. Full-screen pasted text, composed
drafts, initial prompts and model/tool output remain literal. In plain/JSON mode,
each input line is direct input; use `/compose` for literal command text. Full-screen
receipts show the complete scrollable result with terminal controls escaped.

## Adopting the saved edit

After saving, use `/memory refresh`, then `/continue`. Until refresh, active session
memory and consumed recordings retain their previous selection. A disabled document
stays disabled, and memory loading stays off until explicitly refreshed. Combined
memory/context/storage limits or custom recording requirements can reject refresh
after a successful save; the saved edit still exists.

Replacement affects the current saved document. It does not rewrite earlier
sessions, provider requests, backups or receipt copies. Free-form interpretation,
automatic extraction remain planned. Structured assistant proposals can now be
selected for explicit review and confirmation.
