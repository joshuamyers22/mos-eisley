# Save selected text from an assistant reply

Choose an exact span from a completed assistant reply and review it for memory:

```text
/memory review-text project 0 "Use pytest for this project."
```

The source reply can be ordinary prose. Supply the displayed zero-based message
index, explicit `user` or `project` scope, and a JSON string containing the exact
text to append. Project scope uses the session's retained root or mapping. User
scope is available across projects. JSON escapes preserve quotes and newlines:

```text
/memory review-text user 0 "Prefer concise answers.\nUse \"plain language\"."
```

The text must occur exactly once in the chosen assistant reply, including
overlapping occurrences. Missing or repeated matches reject; choose a longer unique
span. Matching is case-sensitive, without Unicode normalization, Markdown parsing
or whitespace cleanup. Mos does not infer which suggestion you meant or extract
preferences from a whole transcript. User prompts, files, tool output and review
agent summaries cannot be selected through this command.

## Review and save

The review displays the complete assistant reply, selected text, target and complete
resulting memory. JSON additionally exposes character offsets and the source
session, prompt and answer. No memory store is created by inspecting a reply.
Review the text and scope, then use the existing proposal confirmation controls:

```text
/memory apply-proposal PREVIEW_SHA256
```

Cancel with `/memory discard-proposal`. The selected text is appended using the
existing blank-line separator; other saved text and enabled state are preserved.
For a reviewed edit or removal, use [exact replacement](CONVERSATION_MEMORY_REPLACE.md)
or [selective forgetting](CONVERSATION_MEMORY_FORGET.md).

This shares one pending review with [structured assistant proposals](CONVERSATION_MEMORY_PROPOSALS.md),
replacement and forgetting. A new scoped preview command invalidates the previous
review even if the new request fails. Valid ordinary writes invalidate it before
storage access; inspection retains it. The hash binds a distinct selection operation,
complete source, exact span offsets, target, before state, result and fresh review
identifier. A change anywhere in the source reply rejects confirmation, even when
the chosen span itself is unchanged. Saved JSON receipts identify the operation.

Apply checks the current memory hash, including expected absence, under the existing
exclusive lock. Concurrent creation or edits reject instead of being overwritten.
A matching attempt consumes the review before writing. If publication succeeds but
a later step fails, the edit may already exist; inspect memory and create a fresh
review. Existing private-file and local integrity boundaries remain in force.

Commands must fit on one line within 8,000 characters. The complete result must fit
the 32-KiB UTF-8 document limit before a review is created. Empty/whitespace-only
selection, invalid JSON, extra arguments and invalid UTF-8 reject. Full-screen
receipts escape terminal controls and keep the complete source/result scrollable.

Only direct terminal controls can create or apply reviews. Pasted text, composed
drafts, initial prompts and model output remain literal. In plain/JSON mode, input
lines are direct controls; use `/compose` for literal command text. Stop active
work first; these commands pause queued work without making a model request.

Use `/memory refresh`, then `/continue` to adopt saved changes. Disabled selection
and document state follow the existing refresh rules. Refresh can independently
reject context/storage limits or require a custom replacement cassette. Earlier
sessions and backups are not rewritten. Reviews disappear on exit, resume or
directory handoff; a retained reply can be selected again for a fresh review.
Automatic extraction and general natural-language interpretation remain planned.
