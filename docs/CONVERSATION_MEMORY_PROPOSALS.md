# Review an assistant memory proposal

Assistant replies never save memory on their own. To review a suggestion, ask for
a reply containing only one of these JSON objects:

```json
{"operation":"append","text":"Use pytest for this project."}
```

```json
{"operation":"replace","old":"Use the old runner.","new":"Use pytest."}
```

```json
{"operation":"forget","old":"Use the old runner."}
```

Select that completed chat reply using the displayed message index and choose the
scope yourself. Indices start at zero, matching `You [0]` in the full-screen
terminal and the JSON message event's `index`:

```text
/memory review-proposal project 0
```

Use `user` for preferences to reuse across projects. Project scope uses the retained
session root or mapping. A proposal cannot choose its own scope, target path,
permissions or execution action. Review/judge output, unfinished messages, user
prompts and arbitrary files cannot be selected as assistant chat replies.

## Review, confirm or discard

The receipt shows the source message index, proposed operation, assistant reply,
selected target and complete resulting memory. JSON also contains the source
session/prompt/answer, source hash and full before snapshot. The terminal escapes
control characters and keeps the complete result scrollable. Review the actual
text and scope before confirming:

```text
/memory apply-proposal PREVIEW_SHA256
```

Or cancel with `/memory discard-proposal`. Receiving or inspecting a proposal does
not create a memory store. Only explicit confirmation saves it. Accepted documents
retain the `explicit_user` source: the user authorized this write. The saved receipt
identifies the assistant source and proposal; durable documents do not introduce a
new provenance schema.

There is one pending memory review per terminal session, shared with selective
forgetting and exact replacement. A new scoped preview command invalidates the
previous review of any kind, even when the new request fails. Valid ordinary memory
writes invalidate it before storage access; inspection retains it. Wrong hashes
cannot apply. Exiting, resuming or switching directories discards pending reviews.
After resume, you can select a retained reply again to obtain a fresh review.

## Validation and consistency

The whole assistant reply must be a single JSON object within 8,000 characters,
without code fences or surrounding prose. Only the fields shown above are accepted.
Duplicate keys, extra fields, invalid types/UTF-8, empty strings and unchanged
replacement text reject. JSON escapes support newlines and quotes. No automatic
extraction, transcript inference or natural-language parsing occurs.

Append preserves the current text and uses the existing blank-line separator.
Replace/forget require exactly one occurrence, including overlapping matches;
matching is case-sensitive with no Unicode normalization or whitespace cleanup.
The complete result must fit the 32-KiB UTF-8 document limit before review. Existing
document enabled state is preserved; a newly accepted scope starts enabled.

Confirmation binds the operation, source session/message/prompt/answer, chosen
scope and target, full before state, complete result and fresh review identifier.
The source is rechecked before apply. The current memory hash, or expected absence,
is checked under the exclusive store lock. Concurrent creation, edits, clearing or
enabled-state changes reject instead of being overwritten. Private-file and local
integrity protections still apply; hostile same-user rollback or parent-directory
replacement remains outside that model.

A matching apply consumes its review before writing. If a write fails after
publication, the edit may already exist: inspect saved memory and create a fresh
review. Do not replay an old token expecting rollback.

Controls require idle work and pause the queue without creating a model request.
Pasted/composed text, initial prompts and model/tool output cannot invoke controls.
Plain/JSON input lines are direct commands; use `/compose` for literal command text.

Saved edits do not change the current session selection until `/memory refresh`;
then use `/continue`. Memory loading remains off until explicitly refreshed, and
disabled documents stay disabled. Refresh can independently reject combined context
or storage limits or require a custom replacement cassette. Historical sessions,
provider requests and backups are not rewritten. This feature works with the
existing recorded terminal; it adds no live provider dispatch or automatic memory
generation. Free-form suggestion extraction remains planned.
