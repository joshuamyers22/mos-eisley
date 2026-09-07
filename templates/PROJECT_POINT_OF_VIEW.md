# Project Point of View and Engineering Practices

Use this as an editable project document. Mos Eisley's planned template attachment
feature is not implemented yet. Copy it to a chosen project path, fill applicable
sections, and explicitly select it as context. Do not overwrite existing guidance.
Delete irrelevant examples and leave unknown choices explicitly unresolved.

## Identity and scope

- Project and workspace:
- Owner:
- Template ID/version:
- Upstream source/revision and digest, if derived:
- Project brief and accepted ADRs:
- Applicable components/languages/workflows:
- Last reviewed and next review trigger:

This document records preferences and accepted project requirements. It grants no
tool, network, credential, budget, deployment, or memory-retrieval authority.
Current user direction and mandatory trusted policy govern the task. The template
cannot approve itself or turn a preference into a requirement.

## Preferences and accepted requirements

Use stable IDs. Mark a requirement accepted only with its project-brief/ADR or
explicit user-decision reference. A justified departure from a preference needs a
concise rationale and verification, not a new permission ritual.

| ID | Kind | Practice | Applies when | Rationale/evidence | Acceptance reference |
|---|---|---|---|---|---|
| ENG-001 | advisory | Prefer simple, maintainable code; earn complexity with evidence. | Relevant implementation | State the local tradeoff. | N/A until accepted |
| ENG-002 | advisory | Measure correctness, relevant efficiency, and whole-task cost together. | Coding/delegation | Include integration and rework. | N/A until accepted |
| PROJECT-001 | advisory / accepted requirement | Fill in project-specific behavior. | Define scope. | Link evidence. | Link decision if required. |

Choose language/library, architecture, statistical method, deployment, and
observability defaults for this project. Do not inherit them merely because the
upstream template uses them.

## Project overrides and departures

| Rule ID | Project choice/departure | Reason and risk | Evidence/check | Decision reference or owner |
|---|---|---|---|---|
| | | | | |

State the ordering of selected base templates and project overrides. Resolve
contradictions visibly; do not use filename order or nearest-directory shadowing.
Changes here must not alter another project's defaults.

## Creator, coding children, and verification

- Required behavior and failure cases:
- Creator-authored plan and executable-test references:
- Critic/judge rubric and blocking findings:
- Creator approval of exact plan/test revisions:
- Coding-child scope, interfaces, and integration owner:
- Quality gate and task-relevant performance evidence:

| Rubric ID | Requirement/outcome | Evidence | Passing threshold | Blocking or advisory |
|---|---|---|---|---|
| | | | | |

- Maximum task cost, elapsed time, and iterations within trusted limits:
- New evidence required for another verification pass:
- Diminishing-return stop and domain-input triggers:
- Unresolved findings and disposition:

These are ceilings, not spending targets. Children implement against creator-written
tests; proposed test corrections return to creator and critic/judge review.

## Logging and improvement conventions for the project being built

- Named operational decisions or user journeys to observe:
- Event schema/version and stable event/error codes:
- Allowed fields, redaction, and forbidden content:
- Diagnostic sink versus mandatory audit-record failure behavior:
- Selected sink, access, retention, capacity, and sampling/drop policy:
- Review cadence, owner, and scoped query references:
- Baseline, later assessment window, regression checks, and guardrails:
- Rollback/stop condition and normal change authority:

These choices do not redirect Mos Eisley's own private telemetry or authorize data
export. Record safe aggregates and evidence links, not raw logs or private inputs.

## Memory and note conventions

- Private project-memory location and size/entry limits:
- Stable entry keys, evidence references, and last-verified dates:
- Explicit session selection or resume for historical content:
- Private ignored scratch location and cleanup:
- When a work note is warranted; owner and review/delete date:
- Closure destinations: verified memory, tests, ADRs, docs, or issue:
- Sanitized project-document publication scope, if explicitly requested:

Do not place actual memory, session summaries, investigation results, raw telemetry,
secrets, private/client data, or reasoning in this template. Binding it must not
automatically load historical content. Memory is an evidence index; verify its
claims before relying on them.

## Adoption and updates

- Exact selected snapshot and approved project overrides:
- Existing files preserved and proposed diff reviewed:
- Outstanding conflicts or missing required evidence:
- In-flight plan/test approvals affected by this revision:
- Detachment or replacement scope:

Updates apply only to this project's binding at a safe task boundary. Retain the
prior snapshot for historical provenance; detaching does not delete project work.
