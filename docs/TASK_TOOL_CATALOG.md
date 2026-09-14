# Runtime tool-catalog selection

Runtime tool-catalog selection exposes only approved, task-applicable tool schemas
to one recorded author request. It is a schema-only G1 boundary: it does not start
an MCP server, install an integration, dispatch a call or grant execution,
credential, provider, spending, continuation or review authority. The recorded
controller's tool-call limit remains zero.

Start with the editable
[catalog](../templates/RUNTIME_TOOL_CATALOG_EXAMPLE.json) and
[selection](../templates/RUNTIME_TOOL_SELECTION_EXAMPLE.json) examples. The catalog
must be reviewed metadata under the same owner-policy digest as the selected frozen
author profile. Compute the SHA-256 of the exact completed catalog file and place it
in the selection file. Then launch both files with automatic profile acquisition:

```sh
mos --plain -C /path/to/project \
  --task-profile-selection /path/to/semantic-task-discovery.json \
  --task-profile-policy /path/to/private/policy.json \
  --task-guidance-storage /path/to/private/guidance-storage \
  --task-tool-catalog /path/to/runtime-tool-catalog.json \
  --task-tool-selection /path/to/runtime-tool-selection.json
```

Catalog and selection are required together, and they require automatic author
profile acquisition. Their exact bytes are loaded and pinned for the launch.
Directory handoff clears both paths with the other project-specific inputs.

## Contract

The strict version-1 catalog is limited to 256 KiB and contains one project,
catalog identity/revision, owner-policy digest and at most 128 canonical tool
definitions. Every entry records its exact schema SHA-256 and canonical byte count,
owner-approved authorization status, catalog availability and overlap peers. The
catalog is metadata only; it contains no command, URL, environment, credential or
server-start configuration.

The strict version-1 selection is limited to 128 KiB. It pins the exact catalog-file
SHA-256, identity, revision, project and policy. Up to 64 decisions each bind one
unique queued-message SHA-256 to the already selected profile and work-unit revision.
Every decision must account for the full ordered catalog inventory and records each
tool's required/optional status, selected/omitted status and nonblank reason.

At `/context` preview and immediately before every non-review request, acquisition:

1. hashes the exact queued author text and requires one matching tool decision;
2. reacquires the guarded author profile and checks the project, policy, profile ID
   and work-unit revision;
3. reconstructs the complete profile tool inventory from the pinned catalog and
   decision; and
4. admits only selected canonical definitions into the exact model request.

A stale catalog pin, altered schema metadata, incomplete/reordered inventory,
missing task decision, mismatched profile/work, required omission, selected
unauthorized tool or selected unavailable/unknown tool fails before the entry becomes
running or consumes an attempt. Optional omissions and selected overlaps remain
visible diagnostics. Request size admission provides the final fail-closed bound if
selected schemas cannot fit.

Saved admission retains text-free source, decision and task hashes, catalog
identity/revision, selected/omitted IDs and the required per-tool manifest metadata,
including bounded selection reasons. Neither selected nor unselected schema bodies,
private task text, nor catalog descriptions are copied into the admission. Unselected
definitions and all manifest metadata stay out of the model request. Review requests
never acquire author tools.

## Acceptance boundary

Fixtures cover exact request/preview selection, omitted-schema exclusion, required
omission, unavailable and unauthorized tools, stale catalog identity, complete
inventory ordering, exact task binding, schema metadata tampering, duplicate JSON
keys, review isolation and the plain terminal. This proves deterministic selection
from supplied approved metadata. It does not perform live MCP discovery or prove a
catalog availability claim is current. If future live discovery is required, it must
use the separately authorized MCP boundary; this selector itself will not start a
server or gain dispatch authority.
