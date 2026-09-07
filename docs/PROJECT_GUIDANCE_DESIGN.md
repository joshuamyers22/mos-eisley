# Production-template adoption decisions

Mos Eisley should adopt the runtime mechanisms for structured operational events,
bounded evidence handling, and project-specific guidance. Engineering opinions
remain editable per-project defaults. The telemetry platform itself remains a
separate optional integration. This is a planning amendment, not implemented runtime
support or an upgrade of the production-template repository.

## Sources and scope

Reviewed the updated local working tree at
`/Users/josh/Projects/production-project-template`, including uncommitted and newly
added documents. Its Git base alone does not identify these updates; see the
companion [source manifest](PRODUCTION_TEMPLATE_REVIEW_SOURCES.json) for file hashes
and base commit.
No claim is made that these files have been published or production-validated.

Primary inputs were `PERSONAL_ENGINEERING_DEFAULTS.md`,
`docs/OBSERVABILITY_AND_IMPROVEMENT.md`, `docs/TELEMETRY_PLAN.md`,
`schemas/telemetry-event.schema.json`, `docs/AGENT_MEMORY_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, and the memory/work-note/review templates.
The source research summaries are background: this amendment does not adopt their
quantitative research claims as evidence of Mos Eisley performance.

## Decision matrix

| Topic | Put in Mos Eisley's product plan | Keep project-specific or separate |
|---|---|---|
| Structured logging | Stable versioned event/error mapping, bounded fields, privacy, correlation, failure and retention contracts (§17.5). | Application-specific signals, SLOs, libraries, sinks, and review cadence. |
| Telemetry platform | Optional export/query adapter with explicit owner-scoped access and bounded failures. | `telem` deployment, SSD/HDD topology, Parquet compaction, DuckDB, Grafana, shipping, host metrics and alerts. |
| Improvement loop | Scoped aggregate review, observed versus inferred findings, reproducible baseline and later assessment, normal change authorization. | Which operational question matters, domain metrics, effect thresholds and ownership. |
| Project memory | Bounded keyed evidence index, stale-entry correction, explicit historical selection, private owner/project storage (§17.6). | Which facts are durable, size limits, and a deliberate sanitized documentation export. |
| Notes | Private scratch, concise evidence-linked handoffs/investigations, expiry and promotion/closure. | When a tracked project document is useful and where approved records live. |
| Verification loops | Requirement-linked evidence, resource ceilings, stop rules, creator-authored tests and role isolation (§15.7). | Rubric weights, domain checks, risk criteria and performance targets. |
| Engineering point of view | Per-project attach/show/update/detach, pinned snapshots, overrides, effective precedence and scoped role context (§16.6). | Python/C++ preferences, libraries, architecture, statistical methods, deployment choices and justified departures. |

## Adaptations required

- **Fresh-session privacy:** the source's startup memory-reading default does not
  apply automatically. Memory/notes require explicit selection or same-owner
  resume. A static project-guidance binding is not permission to retrieve history.
- **Ownership:** the source telemetry estate cannot become a pool of Mos Eisley
  users' data. A sink must enforce individual ownership, including derived records.
  Public project guidance may be shared; private runtime records are not copied
  into it. The software being built may have its own separate observability policy.
- **Audit durability:** optional logs may be dropped under a declared loss contract;
  required authorization/audit/spend records cannot inherit that behavior.
- **Cost authority:** query-time telemetry repricing is diagnostic. It cannot change
  reserved/settled cost, permit retries, or free an uncertain reservation.
- **Schema compatibility:** translate versioned lifecycle events explicitly. The
  source schema's snake-case names do not accept all current dot-named examples;
  optional free-text/stack fields are not automatically allowed in Mos Eisley.
- **Evidence authority:** notes and recommendations do not supersede accepted
  requirements, executable evidence, or trusted policy. Observing a pattern does
  not authorize an agent to rewrite its own prompts, safety rules, or production.
- **Scope:** no vector database, automatic cross-session recall, model training,
  estate-wide exporter, or autonomous improvement scheduler is added by default.

## Project-by-project use

The reusable starter is [PROJECT_POINT_OF_VIEW.md](../templates/PROJECT_POINT_OF_VIEW.md).
It is usable now as a manually selected project document. Future automatic support
binds a reviewed snapshot and local overrides in trusted owner configuration.

For example, a CLI project can select a Python engineering profile and its own
logging policy; a quantitative project can select a statistical point of view and
add its own data/validation requirements; a latency-sensitive C++ project can choose
different allocation and latency criteria. A change to one profile binding cannot
change the others. Advisory departures record rationale and evidence. Accepted
requirements are traced to the project's brief or ADR, not self-certified by the
template.

During creator-led coding, the creator uses the effective project rubric to write
the plan and tests; critic and judge review against the same frozen rubric; coding
children receive the relevant approved requirements. Private creator notes stay
outside independent review contexts.

## Delivery and verification

Add declarative project guidance with trusted project configuration and the
conversation controller. Add explicit memory/note retrieval with private storage;
repository writes and publication keep their existing gates. Add operational event
mapping alongside provider/controller work, then optional external adapters only
after their isolation and failure checks pass.

The plan's §§16.6 and 17.5–17.6 specify acceptance coverage for two-project/two-user
isolation, conflicting or changed templates, frozen role contexts, explicit history
selection, export/deletion, telemetry sanitization and overload, and required audit
failures. Evaluate memory and improvement workflows on correct task outcomes with
disjoint assessment data; lower token use alone is insufficient.
