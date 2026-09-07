# Production-template adoption decisions

Mos Eisley should adopt the runtime mechanisms for structured operational events,
bounded evidence handling, and project-specific guidance. Engineering opinions
remain editable per-project defaults. The telemetry platform itself remains a
separate optional integration. This is a planning amendment, not implemented runtime
support or an upgrade of the production-template repository.

## Sources and scope

Re-reviewed the published GitHub `main` at
[`d59f3e661a1fa3456505cf36f91b51f4a1c873ac`](https://github.com/joshuamyers22/production-project-template/commit/d59f3e661a1fa3456505cf36f91b51f4a1c873ac).
All 15 files hashed in the earlier local-working-tree review match the published
Git blobs exactly. The earlier architectural decisions therefore still apply; this
revision replaces local-only provenance and expands review to the published
implementation, generated example, and production-readiness checklist. See the
companion [source manifest](PRODUCTION_TEMPLATE_REVIEW_SOURCES.json) for the exact
GitHub revision, source hashes, comparison, and validation scope. Published source
and passing example tests do not establish production readiness in Mos Eisley.

Primary inputs were `PERSONAL_ENGINEERING_DEFAULTS.md`,
`docs/OBSERVABILITY_AND_IMPROVEMENT.md`, `docs/TELEMETRY_PLAN.md`,
`schemas/telemetry-event.schema.json`, `docs/AGENT_MEMORY_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, and the memory/work-note/review templates.
The source research summaries are background: this amendment does not adopt their
quantitative research claims as evidence of Mos Eisley performance.

## Published implementation and reuse decision

The upstream update includes working code, not only telemetry plans:

- [`python-telemetry`](https://github.com/joshuamyers22/production-project-template/tree/d59f3e661a1fa3456505cf36f91b51f4a1c873ac/archetypes/python-telemetry)
  provides a standard-library runtime with explicit composition, bounded event
  construction, attribute sanitization, scoped run context, a sink protocol, and a
  local JSONL spool. Queue admission is separate from fsync-confirmed durability;
  closed-file consumers require the checksum sidecar commit marker.
- The API-service archetype has a structured Python logging formatter. Its optional
  `safe_message` switch permits free text, so it is not a ready-made privacy boundary
  for an agent handling prompts, tools, and provider errors.
- The C++ archetype has a fixed-buffer encoder for the shared envelope. Queueing,
  writing, and target-hardware latency evidence remain separate; it is not needed
  by Mos Eisley's Python runtime.
- Shared archetype files supply agent instructions, memory/notes, schema, and review
  templates. The generator applies shared then archetype files to a new destination;
  it does not implement Mos Eisley's planned per-project attachment/update workflow.

**Decision:** prefer evaluating the pinned Python core/spool behind a Mos-owned sink
adapter before writing equivalent diagnostic infrastructure. Choose a versioned
package or reviewed source extraction with provenance when implementation begins;
do not depend on unresolved archetype placeholders or a mutable Git branch. Retain
project-selected backends and keep the estate platform optional. No upstream runtime
code is imported, installed, or enabled by this documentation review.

The adapter must enforce a narrower field contract before upstream event creation.
Allowlisting an attribute name or recognizing common secret patterns does not prove
arbitrary values are safe. Constrain identifiers, nested attributes, error metadata,
and correlation fields; omit free-text messages and traceback locations unless
separately reviewed. Test with Mos-specific prompt/tool/provider-output canaries.

Adopt upstream's accepted/durable/pending distinction, independently readable health
and drop/error counters, bounded shutdown, quota/drop-new behavior, and sidecar-only
publication checks if using its spool. Partition and authorize every spool by owner;
the emitter's run ID alone does not establish user isolation. Recheck actual service
account, filesystem, overload, crash and retention behavior before rollout using the
published [readiness checklist](https://github.com/joshuamyers22/production-project-template/blob/d59f3e661a1fa3456505cf36f91b51f4a1c873ac/archetypes/python-telemetry/PRODUCTION_READINESS.md).
Required audit and spending transactions remain on their own durable path.

## Decision matrix

| Topic | Put in Mos Eisley's product plan | Keep project-specific or separate |
|---|---|---|
| Structured logging | Stable versioned event/error mapping, bounded fields, privacy, correlation, failure and retention contracts (§17.5). | Application-specific signals, SLOs, libraries, sinks, and review cadence. |
| Telemetry code and platform | Evaluate reuse of the published Python core/local spool behind a Mos-owned adapter; add independent health, explicit durability semantics, and optional owner-scoped export/query. | `telem` deployment, SSD/HDD topology, Parquet compaction, DuckDB, Grafana, shipping, host metrics and alerts. |
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

For this re-review, extracted only `src/`, `tests/`, and `schemas/` from the pinned
published `examples/python-telemetry` into a temporary directory and ran its existing
`unittest` suite under Python 3.12. All **26 tests passed**, covering event/config
contracts, sanitization, schema validation, disk pressure, shutdown, fork handling,
and SIGKILL/partial-tail recovery. The snapshot was removed after execution. No
dependencies were installed and no source working tree was changed by the tests.
This was a focused upstream example check, not the full template gate, a C++ test
run, a comprehensive security audit, or Mos Eisley integration/production validation.

The plan's §§16.6 and 17.5–17.6 specify acceptance coverage for two-project/two-user
isolation, conflicting or changed templates, frozen role contexts, explicit history
selection, export/deletion, telemetry sanitization and overload, and required audit
failures. Evaluate memory and improvement workflows on correct task outcomes with
disjoint assessment data; lower token use alone is insufficient.
