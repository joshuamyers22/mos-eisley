# G1 scoped conversation admission

## Status

Implemented on 2026-09-20 as the first G1 runtime slice in plan §26.4. The
existing conversation controller can now resolve one immutable task profile for a
queued message, validate its owner/project/workspace scope and offline diagnostics,
classify selected context, and bind the result to the saved request admission before
provider dispatch.

This slice follows the repository structure and verification practices in the local
`production-project-template`: strict versioned records, pure admission policy,
injected runtime dependencies, fail-closed boundary checks and one repository-wide
verification gate.

## Runtime boundary

Trusted composition supplies three values to `ConversationController` together:

- the expected `OwnerProjectScope` for the conversation;
- a resolver returning the `ScopedTaskProfile` for a message index, or `None`;
- an optional `ToolDispatcher` whose definitions form the trusted available catalog.

Ambient scope or tools without a profile resolver are rejected. A resolved profile
is revalidated immediately before the running state is saved. Admission rejects a
scope mismatch, any profile error diagnostic, altered instruction content, duplicate
catalog definitions, a missing selected tool, or a selected tool schema that differs
from the manifest. A failure consumes no model attempt and saves no running state.

Only selected tool definitions enter the model request. The scoped dispatcher also
rejects execution of an unselected call. Supplying a profile does not itself grant
tool, credential, spending, or machine authority; those remain properties of the
injected dispatcher and their existing gates. The default recorded CLI supplies no
profile resolver or tool dispatcher, so its authority is unchanged.

## Context classes and retained evidence

Selected stable instructions and temporary/unknown task state are placed in separate
labelled system sections. Saved user/project memory remains the only reusable-memory
class. The schema-2 request admission retains only bounded provenance:

- exact reusable-memory scope, revision and digest references;
- stable-instruction and temporary-task-state IDs;
- profile, work-unit, policy and scope identity;
- selected instruction/tool IDs, visible warning codes and profile sizes.

Instruction and memory text is not copied into the admission record. Read-only
admission inspection reports these identities and counts without expanding content.
Schema-1 admissions remain readable. Both private snapshot and SQLite stores preserve
the schema-2 profile record.

## Completed lifecycle connection

The original injected resolver remains available for explicitly supplied standalone
profiles. Checkpoint continuation now uses
[work-unit-owned acquisition](G1_WORK_UNIT_PROFILE_ACQUISITION.md): the selected work
unit binds exact private instruction material, and the checkpoint store reconstructs
and rechecks it immediately before dispatch. Schema-6 admission records text-free
checkpoint/bundle provenance. `/context` remains a state-only preview and cannot
invent runtime profile material. Checkpoint closure, fresh continuation, author
compaction and advisory pressure are also implemented.
