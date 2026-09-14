# Current task-state acquisition

Recorded `chat` and `resume` sessions can acquire temporary task context from one
explicitly selected G0 task-state archive. The archive remains immutable and private;
the selection file is the launch's current pointer. Acquisition happens for every
non-review request before the entry runs or consumes an attempt.

Start with the editable
[current task-state selection example](../templates/TASK_STATE_SELECTION_EXAMPLE.json).
Copy the bundle digest/revision, checkpoint identity/digest and checkpoint's current
work-unit reference from a verified archive, save the selection as an owner-only file,
and launch with its archive root:

```sh
chmod 600 /path/to/current-task-state.json
mos --plain -C /path/to/project \
  --task-state-selection /path/to/current-task-state.json \
  --task-state-storage /path/to/private/task-state-archives
```

The selection's exact launch bytes are pinned. Each request reopens the private
selection, requires it to be unchanged, then uses the G0 replay boundary to verify
the archive's owner/project/workspace scope, canonical manifest and bundle, complete
artifact inventory, digests, evidence views and internal checkpoint/work-unit
references. A second selection read catches changes during acquisition. Directory
switches clear the selection rather than carrying task state to another workspace.

The request receives a bounded canonical projection containing the checkpoint, its
current work unit, applicable clause records and active decision records. Evidence
identities, verification status, artifact freshness and requirement bindings remain,
but evidence-view text is omitted and recorded by evidence ID so logs or retrieved
text are not promoted into system instructions. The projection is capped at 256 KiB
and still passes the existing context and complete-request byte admissions.

SQLite stores this temporary context as its own immutable entry artifact. The saved
request admission binds its digest and byte count, archive/bundle/checkpoint identity,
current work-unit revision and exact model-request digest. A task profile used with
the same request must select that work unit and binds the separate task-state artifact
digest; reusable memory remains a different source.

Ordinary acquisition verifies archive integrity and current-pointer stability. The separate
[checkpoint-closure boundary](TASK_STATE_CHECKPOINT_CLOSURE.md) can now append a
verified terminal work revision and atomically advance that pointer without resetting
state or claiming continuation. The subsequent
[fresh-context continuation boundary](TASK_STATE_CONTINUATION.md) accepts a separate
explicit selection, inspects live Git and relevant files, marks old passes stale when
the workspace changed, and atomically binds one new session to the selected
outstanding work. Ordinary current-state acquisition still makes none of those
claims. Neither path re-runs tests, resets ledgers, replays uncertain effects, or
grants tools, credentials, spending or other authority.
