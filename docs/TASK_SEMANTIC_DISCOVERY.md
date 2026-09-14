# Validated semantic task discovery

Validated semantic task discovery selects one already reviewed, frozen creator or
coder profile for an exact queued author message. It is an inert private selection
boundary: it does not generate guidance, select tools, start servers or grant
execution, credential, provider, spending, continuation or review authority.

Use the editable
[semantic-discovery example](../templates/TASK_SEMANTIC_DISCOVERY_EXAMPLE.json) as a
shape reference. Pass the resulting private file through the existing profile option:

```sh
mos --plain -C /path/to/project \
  --task-profile-selection /path/to/semantic-task-discovery.json \
  --task-profile-policy /path/to/private/policy.json \
  --task-guidance-storage /path/to/private/guidance-storage
```

## Contract

The strict version-1 plan is limited to 128 KiB and contains:

- one project and up to 16 complete frozen author-profile candidates, all bound to
  the same owner-policy digest;
- up to 64 decisions with unique IDs and exact queued-message SHA-256 digests;
- one bounded category and private objective per decision;
- one or more exact character ranges and quotes from the queued author message;
- one selected profile whose work-unit reference exactly matches the decision; and
- an ordered, reasoned omission for every other candidate.

Categories are implementation, debugging, verification, review, documentation,
research, maintenance and other. The category and objective are supplied semantic
claims, not model verdicts. `ambiguous` must be false. Unknown fields, duplicate JSON
keys, reviewer candidates, duplicate message digests, incomplete omissions, mixed
projects or policies, oversized input and malformed UTF-8 fail closed.

At `/context` preview and immediately before each non-review request, the controller
hashes the exact queued author text, requires one matching decision and verifies each
quoted source range byte-for-character against that text. It then opens only the
selected frozen role context through the existing guarded boundary and revalidates
the project, assessment, policy, snapshot and context. A missing decision, changed
message, stale role source or mismatched quote fails before the entry becomes running
or consumes a recorded attempt. Review requests never acquire author discovery.

The semantic objective, source quotes, selection rationale and omission reasons stay
in the private launch file and do not enter the model request or saved request
admission. Admission retains only the discovery/decision/task digests, category,
candidate IDs, selected ID and complete omitted IDs. The model receives only guidance
from the selected frozen role packet. The exact discovery-file bytes are pinned for
the launch; editing the path does not silently change a running session.

## Acceptance boundary

Fixtures cover exact selection and preview/admission equivalence, stale task text,
source-range mismatch, malformed inventories and duplicate keys, forged reviewer
candidates, text-free SQLite recovery and the line terminal. This proves structural
and source binding for a supplied semantic decision. It does not prove that the
category or profile choice is semantically correct or better than the baseline; live
quality claims remain behind the G3 held-out evaluation gate. A separate
[runtime tool-catalog boundary](TASK_TOOL_CATALOG.md) may consume the resulting exact
profile/task identity; semantic discovery itself still does not select tools.
