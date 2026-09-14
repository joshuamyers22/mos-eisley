# Automatic task-profile acquisition

Recorded `chat` and `resume` sessions can acquire an inert task profile from one
explicitly reviewed, frozen creator or coder guidance packet. Acquisition happens at
each non-review request boundary. It rechecks the current project identity, complete
guidance assessment, exact private owner policy, immutable role snapshot and selected
context while holding the existing private guidance lock.

Start with the editable
[task-profile selection example](../templates/TASK_PROFILE_SELECTION_EXAMPLE.json).
Copy `snapshot_sha256`, `context_sha256`, `role` and `scope` from a reviewed
`mos guidance-context freeze` receipt. Name the project and intended work-unit
reference, then pin the same reviewed policy digest used to freeze the role packet.
Only creator and coder contexts are accepted; critic and judge contexts cannot become
author instructions. The work-unit reference alone is request provenance. When
[current task-state acquisition](TASK_STATE_ACQUISITION.md) is also selected, both
sources must name the same work unit; neither grants continuation authority.

```sh
mos --plain -C /path/to/project \
  --task-profile-selection /path/to/task-profile-selection.json \
  --task-profile-policy /path/to/private/policy.json \
  --task-guidance-storage /path/to/private/guidance-storage
```

Selection and policy are required together. The selection file's exact bytes are
pinned for the launch; editing it does not silently change an active session. The
referenced guidance, assessment, policy and project are revalidated for every request.
If any become stale, acquisition fails before the entry becomes running and before a
provider attempt. `/context` uses the same acquisition boundary for its preview.
Directory switches clear the selection and policy paths rather than carrying a task
profile into another workspace.

The runtime profile contains only the selected role rules and their applicability,
rationale, checks and approved override reasons. The saved request admission records
text-free hashes, the work-unit revision, explicit requirement omissions and the exact
request binding. Private policy prose, source documents, creator history and task
state remain outside the model request.

An optional [runtime tool-catalog selection](TASK_TOOL_CATALOG.md) can now add only
the canonical schemas selected for the exact queued author task. The catalog and its
separate decision file are both explicitly supplied and byte-pinned; no server is
started, the recorded controller's tool-call limit remains zero, and profile records
grant no execution, provider, spend, credential or continuation authority. The same
launch option also accepts a
[validated semantic discovery](TASK_SEMANTIC_DISCOVERY.md) that selects one candidate
frozen author packet for an exact queued message. Automatic generation of semantic
or tool decisions and runtime route selection remain future work.
