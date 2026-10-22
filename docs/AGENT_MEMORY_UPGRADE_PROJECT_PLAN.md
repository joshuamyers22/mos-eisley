# Mos Eisley agent memory upgrade plan

Status: proposed implementation contract. Date: 2026-10-06.
This plan specifies production delivery and qualification of memory upgrades;
the features are not implemented or enabled by adding this document. Josh is the
proposed sponsor. Phase 0 must assign implementation, security/data review, and
release owners without treating agent self-review as accountable approval.

## Objective and applicable contracts

Help an owner retain durable project knowledge, find the relevant current facts
for a later task, inspect their evidence, correct them, and see what remains after
forgetting. Preserve private ownership, explicit scope, concurrency protection,
historical reconstruction, provider budgets, and independent review boundaries.

The reviewed source baseline is
[`758f3e4ea8863a0bf4ba55a1e757765a7dba21ca`](https://github.com/joshuamyers22/mos-eisley/tree/758f3e4ea8863a0bf4ba55a1e757765a7dba21ca).
Reconcile implementation with the current main branch and recheck baseline
drift before changing runtime code. Current contracts include
[memory][mos-memory], [assistant proposals][mos-proposals],
[role packets][mos-roles], [current role admission][mos-admission], and the
[agent agreement][mos-agents]. The engineering, threat-model, verification, and
work-note guides selected by that agreement apply to implementation.

The template producer's
[companion plan](https://github.com/joshuamyers22/production-project-template/blob/main/docs/AGENT_MEMORY_UPGRADE_PROJECT_PLAN.md)
owns repository validation/export. The
[reusable plan template](https://github.com/joshuamyers22/production-project-template/blob/main/templates/AGENT_MEMORY_UPGRADE_PLAN.md)
defines the common delivery record. Agree exchange versions and fixtures before
either side's integration release.

## Existing behavior and scope

The current runtime loads complete enabled user/project documents under a 32-KiB
combined content/context bound. Document revisions, hashes, private files, locked
updates, stale-selection checks, and reviewed proposals already exist.
Proposal receipts identify their assistant source, while durable documents use
`explicit_user`; the new schema must distinguish origin from permission to save.
Frozen guidance and guarded local role consumption already exist and should be
extended at their consumer boundaries. [Sources: memory implementation][mos-code],
[proposal contract][mos-proposals], [admission contract][mos-admission].

No automatic remote sync, ambient reviewer-history loading, autonomous policy
rewrite, new provider permission, or model training belongs to this delivery.
Graph and embedding engines are optional later candidates. New live dispatch
wiring remains subject to the existing run, containment, spend, and launch gates.

## Source-linked upgrade requirements

The following contracts are proposed adaptations. External sources motivate
patterns; Mos's tests and requirements establish their local acceptance.

| ID | Deliverable and intended outcome | Blocking acceptance evidence | Sources |
|---|---|---|---|
| MOS-M01 | Versioned keyed entries for preferences, constraints, decisions, current state, and verified lessons. | Stable IDs survive content updates; duplicate keys and unsupported versions reject; limits are enforced before allocation/publication. | [Template scaffold][ppt-memory]; [Hindsight categories][hindsight]; [existing schema][mos-code] |
| MOS-M02 | Separate origin, authorizing action, evidence, verification, and claim status. | Saving an assistant suggestion preserves assistant origin; save approval cannot mark it verified or authorize tools. Legacy unknown values remain explicit. | [Proposal receipt behavior][mos-proposals]; [Graphiti lineage][graphiti] |
| MOS-M03 | Freshness checks, explicit conflict records, and reviewed supersession. | Changed evidence is flagged; conflicting active claims do not silently determine action; historical truth remains distinct from current acceptance. | [Graphiti temporal facts][graphiti]; [template evidence contract][ppt-guide] |
| MOS-M04 | Owner/project/role-filtered lexical recall with bounded results and a pinned small core. | Forbidden entries never reach ranking or output; result order is deterministic; stale indexes and budget overflow fail visibly; zero results is valid. | [Mem0 retrieval signals][mem0]; [MemOS local search][memos]; [Hindsight bounded recall][hindsight] |
| MOS-M05 | Immutable memory-selection receipts and consumer admission checks. | Saved selection reconstructs exact entry revisions; changed policy/store generation prevents stale current admission; historical display grants no authority. | [Existing role packet][mos-roles]; [existing guarded admission][mos-admission]; [Letta versioned memory pattern][letta] |
| MOS-M06 | Reviewed deduplication, correction, and promotion proposals. | Preview binds source/result hashes and target scope; concurrent edits reject; no autonomous mutation or silent semantic merge occurs. | [Existing proposal flow][mos-proposals]; [LangMem foreground/background split][langmem]; [Cognee lesson promotion][cognee] |
| MOS-M07 | Deletion inventory, index invalidation, and explicit disposal of eligible local copies. | Forgotten entries cannot return through cached/indexed recall; restoration does not silently resurrect them; receipts identify historical/backup copies that remain. | [Current retention warning][mos-memory]; [Graphiti invalidation versus deletion][graphiti] |
| MOS-M08 | Explicit template-entry import/update with reviewed source changes. | Import binds repository revision, selected entries, source digest, and destination generation; unchanged retry is idempotent; conflicts receive a preview. | [Template scaffold][ppt-memory]; [Mos reviewed proposals][mos-proposals] |
| MOS-M09 | Operational diagnostics and a repository-task assessment contract. | Safe counters expose failure modes; schema/isolation qualification passes; behavioral claims require later authorized assessment under the production-study gate. | [LongMemEval abilities][longmemeval]; [LoCoMo benchmark][locomo]; [Mos study boundary][mos-readme] |
| MOS-M10 | Conditional semantic/graph retrieval adapter. | Adopt only after a named lexical failure and a measured improvement at fixed budgets; scope, deletion, provenance, and failure behavior pass the same contract. | [Graphiti hybrid search][graphiti]; [Mem0 retrieval][mem0]; [technique tutorials][techniques] |

## Proposed data contract

Use an ADR to choose the authoritative keyed store. SQLite is the initial
candidate because it permits transactional entries and local lexical indexes;
the current memory-file lifecycle remains a compatibility obligation. Do not
assume the existing session database is automatically a suitable memory store.
Document private-file admission, owner/project partitioning, supported SQLite
configuration, locking, WAL/sidecar handling, quotas, and backup/restore first.

Each entry requires a schema version, opaque entry ID, stable scoped key,
owner/project identity, type, bounded text, revision, enabled state, origin,
authorizing action reference, claim status, and evidence-reference list.
Verification date/revision and validity bounds may be absent. Supersession links
must reference an existing same-scope entry and reject cycles. Source hashes
identify bytes; they do not prove semantic correctness or user approval.

Separate claim status (`unverified`, `verified_fact`, `accepted_decision`,
`inference`) from lifecycle (`active`, `superseded`, `deleted`) and computed
freshness (`current`, `changed`, `missing`, `unverifiable`). A verified preference
records evidence of the user's preference, not an externally true world fact.
An accepted decision requires the applicable explicit decision workflow.

Untrusted text and evidence references cannot select a storage path, grant
capabilities, or change requirements/policy. Resolve only explicitly selected
evidence inside an admitted repository/artifact boundary. No link-following or
filesystem crawl is implied by recording a reference.

Phase 0 sets store/entry/query/preview/import/index size and count limits,
transaction durability, supported-platform behavior, and retention rules.
Preserve the existing 32-KiB active-memory cap until a separately reviewed change;
admit provider tokens in addition to bytes where the provider contract supports
it. Unknown versions, ambiguous migrations, and malformed inputs fail visibly.

## Retrieval and run admission

1. Validate owner, exact project identity, role, explicit selection policy, and
   allowed entry states before search. User scope does not authorize private
   project pooling; worktree mappings remain explicit.
2. Include the owner-selected bounded core and mandatory accepted guidance. Search
   discretionary entries using an explicit task query; define tokenizer/version,
   normalization, ranking, stable tie-breaks, and no-result behavior in the ADR.
3. Reject stale derived-index generations, contradictory current guidance, and
   invalid evidence projections. Budget optional recall without silently dropping
   mandatory requirements. Return omission reasons and bounded evidence refs.
4. Freeze entry IDs/revisions, source/store generation, query/ranking version,
   policy/guidance hashes, selected-context digest, and budget outcome. Store any
   sensitive query only in already-authorized private run artifacts, not telemetry.
5. During short local payload preparation, revalidate the current selection and
   produce immutable request bytes. Release locks before provider dispatch.
   Define the admission linearization point and required pre-dispatch recheck;
   edits after admission affect later turns, not the already-frozen payload.

Critic/judge requests receive explicitly selected frozen requirements and evidence.
Private creator memory and conversation history remain excluded unless separately
authorized by the existing role contract. JSON fencing does not replace these
controls; adversarial memory text must also be tested at the assembled boundary.

## Migration and rollback

Legacy v1 Markdown stays readable. Initial conversion wraps the complete document
as an opaque legacy entry rather than inventing fact boundaries or provenance.
Splitting it into keyed facts requires an explicit reviewed proposal. Preserve its
enabled state, scope, source revision, and historical selection; do not mark it
verified or overwrite its meaning during conversion.

Preview conversion with expected source/destination hashes, bounds, and rollback
inventory. Publish source-preserving conversion atomically or through a documented
durable checkpoint protocol. Interrupted migration must leave either the original
readable state or an inspectable recoverable destination. A retry cannot duplicate
entries; a concurrent edit requires a fresh preview.

Keep the new path opt-in through qualification. Disabling it restores the legacy
reader for supported unchanged v1 stores. After v2-only edits, rollback requires
an explicitly reviewed bounded legacy export, or feature disablement while v2
data is retained. Never silently downgrade claim status or provenance to satisfy
an older reader. Keep immutable historical artifacts inspectable.

Deletion has three separate results: exclusion from current recall, reviewed
local-copy disposal, and unresolved external/historical retention. A deletion
tombstone contains only minimal identity/version metadata, with its own retention
policy. Indexes are rebuildable and generation-bound. Restoring backups requires
reconciliation against deletion state; restoring old bytes alone cannot silently
enable deleted entries. Secure erasure of journals/providers is not promised.

## Delivery and acceptance gates

| Phase | Requirements and implementation slice | Exit evidence | Rollback |
|---|---|---|---|
| 0 | Assign owners; inventory current schema/consumers; approve schema, storage, bounds, threat model, exchange, and admission ADRs. | Every requirement has an owner, milestone, blocking test, resource ceiling, and source. Compatibility inventory names supported versions/platforms. | Keep all runtime behavior unchanged. |
| 1 | MOS-M01/02: keyed schema, private storage, provenance, opaque legacy conversion, CLI preview/inspection. | Real-storage concurrency, crash, permission, corruption, bounds, unsupported-version, and migration tests pass. | Disable v2; preserve source and inspectable artifacts. |
| 2 | MOS-M03/07: freshness, conflict/supersession, deletion inventory and tombstones. | Changed/missing evidence and conflict flows are visible; deletion/index/restore tests prevent resurrection. | Disable new recall; retain reviewed state for repair. |
| 3 | MOS-M04/05: lexical recall, frozen selections, recorded controller and role-consumer integration. | Packaged CLI journeys show deterministic scope filtering, current admission, bounded payloads, and exact historical reconstruction. | Use explicit legacy selection or memory off; never silently expand context. |
| 4 | MOS-M06/08: reviewed consolidation and versioned template import/update. | Template export → import → evidence change → reviewed replacement → forget passes consumer contract fixtures. | Disable import/proposals; retain existing accepted entries. |
| 5 | MOS-M09: operational runbook, release gate, later authorized behavioral assessment. | Candidate-specific correctness evidence and accountable release review pass; assessment obeys production prerequisites. | Disable new feature; retain diagnostic aggregates and protected artifacts under policy. |
| 6 | MOS-M10, conditional. | Named baseline failures justify an adapter; fixed-budget benefit and all safety/operational contracts pass. | Return to qualified lexical backend and rebuild derived indexes. |

Phase 1 does not authorize Phase 6. Implementation must first check the latest
baseline for capabilities already delivered. Reuse the existing proposal,
identity, storage, guidance, and admission boundaries rather than creating
independent mechanisms with incompatible semantics.

## Verification matrix

| Risk | Required test and observable outcome |
|---|---|
| Cross-user/project leakage | Two owners and two projects with identical keys and distinctive canaries; unauthorized results and payloads contain none of the other scope's content. |
| Authority spoofing | Memory requesting tools, policy changes, evidence-link execution, or spend cannot alter the independent authorization result. |
| Lost updates | Concurrent edit/import/apply with old hashes rejects; no accepted entry is overwritten without a current preview. |
| Incomplete publication | Inject process death/disk pressure at migration and write boundaries; inspection distinguishes absent, committed, and recoverable states. |
| Stale context | Change store generation, evidence, policy, or guidance between selection and preparation; the consumer rejects stale admission. |
| Budget overflow | Unicode/escaping, large results, mandatory guidance, and malformed records stay within declared read/allocation/request bounds. |
| Replay drift | Same frozen inputs produce identical selection digests and recorded requests; historical view cannot satisfy current admission. |
| Conflicting state | Old/new test-runner facts require explicit accepted supersession; lexical relevance cannot resolve authority. |
| Deleted-entry resurrection | Warm cache, stale index, interrupted deletion, backup restore, and repeat import cannot return a deleted entry without explicit authorized recreation. |
| Consumer mismatch | Unsupported template exchange version rejects before mutation; supported import retries preserve stable entry identity. |

Use real admitted storage and packaged CLI entry points for integration/E2E
evidence; doubles cover isolated provider behavior, not live qualification.
Re-run affected checks after changes and run `make check` for the coherent batch
before publication. Record actual commands/results against the candidate revision.
Plan creation itself does not constitute a passing runtime gate.

## Measurement, operation, and release

Before implementation, record iteration, elapsed-time, and compute ceilings plus
stop/escalation rules. Before performance qualification, agree workload size,
query distribution, concurrency, hardware, p95 latency ceiling, and maximum
context cost. Unfilled thresholds block that qualification; do not substitute
vendor numbers or infer missing outcomes.

Later behavioral assessment compares no-memory/current-document/keyed-lexical
paths with the same task criteria and declared budgets. Define separate development
and assessment tasks, correct-completion rubric, stale/conflict error rates,
abstention, evidence recall, repeated ineffective actions, latency, and context
cost. Public LongMemEval/LoCoMo results are supplemental conversational-memory
evidence; repository decisions and safe coding need local tasks.

Honor the existing production-study gate. Sampling receipts grant no authority;
do not read sampling registries, custodian mappings, label/outcome stores, infer
missing splits/probabilities, or copy prompts, responses, tool output, or outcomes
into sampling artifacts. A failed sampling hook does not stop ordinary work and
cannot establish evaluation eligibility.

Operational events include stable error codes, counts, durations, size/budget
outcomes, and opaque identifiers. Exclude queries, memory text, raw evidence,
full filesystem paths, prompts/transcripts, credentials, and provider payloads.
Runbooks cover stale indexes, conflict repair, disk pressure, failed migration,
backup restore, forgotten-copy inventory, and feature disablement. Required
authorization/audit records retain their own durability contract.

Release requires named accountable review, passing required evidence, documented
supported versions/platforms, a verified rollback journey, source-linked user
documentation, and explicit unresolved-risk dispositions. Claims of better task
performance require the later authorized assessment, not merely schema tests.

## Sources

Checked 2026-10-06; revisions are pinned. Letta's active implementation is
`letta-code`; Graphiti is the open-source engine relevant to Zep. Tutorial and
vendor reports motivate design candidates, not local production guarantees.

[mos-memory]: https://github.com/joshuamyers22/mos-eisley/blob/758f3e4ea8863a0bf4ba55a1e757765a7dba21ca/docs/CONVERSATION_MEMORY.md
[mos-code]: https://github.com/joshuamyers22/mos-eisley/blob/758f3e4ea8863a0bf4ba55a1e757765a7dba21ca/src/mos_eisley/conversation_memory.py
[mos-proposals]: https://github.com/joshuamyers22/mos-eisley/blob/758f3e4ea8863a0bf4ba55a1e757765a7dba21ca/docs/CONVERSATION_MEMORY_PROPOSALS.md
[mos-roles]: https://github.com/joshuamyers22/mos-eisley/blob/758f3e4ea8863a0bf4ba55a1e757765a7dba21ca/docs/PROJECT_GUIDANCE_ROLE_CONTEXT.md
[mos-admission]: https://github.com/joshuamyers22/mos-eisley/blob/758f3e4ea8863a0bf4ba55a1e757765a7dba21ca/docs/PROJECT_GUIDANCE_ROLE_ADMISSION.md
[mos-agents]: https://github.com/joshuamyers22/mos-eisley/blob/758f3e4ea8863a0bf4ba55a1e757765a7dba21ca/AGENTS.md
[mos-readme]: https://github.com/joshuamyers22/mos-eisley/blob/758f3e4ea8863a0bf4ba55a1e757765a7dba21ca/README.md
[ppt-memory]: https://github.com/joshuamyers22/production-project-template/blob/71ad8786d02bc8e5656ec10b43896c5c36336656/archetypes/_shared/PROJECT_MEMORY.md
[ppt-guide]: https://github.com/joshuamyers22/production-project-template/blob/71ad8786d02bc8e5656ec10b43896c5c36336656/docs/AGENT_MEMORY_GUIDE.md
[mem0]: https://github.com/mem0ai/mem0/blob/c93420c49a6b14c3d446bdb156d96811908fd90a/README.md
[graphiti]: https://github.com/getzep/graphiti/blob/aa5bb2706929fce502d99d8c7c4ddbb77bff4995/README.md
[hindsight]: https://github.com/vectorize-io/hindsight/blob/9269b88417ed263e5a8350f2e416ca2b322756b1/README.md
[letta]: https://github.com/letta-ai/letta-code/blob/4b028fab07c69edaac2ddb4f7b9a43573ff20d81/README.md
[memos]: https://github.com/MemTensor/MemOS/blob/a7367d07e55db61099f7b4e2c1108bc5831a24f3/README.md
[langmem]: https://github.com/langchain-ai/langmem/blob/48e3c11f5bb527282c7d5339c6a87a0b35abccfc/README.md
[cognee]: https://github.com/topoteretes/cognee/blob/b32d8afc59e1064d9291b9828a8a147be9cc8bab/README.md
[techniques]: https://github.com/NirDiamant/Agent_Memory_Techniques/blob/4767c0341ccd8b714147334c5f17c26ff99d8e41/README.md
[longmemeval]: https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/README.md
[locomo]: https://github.com/snap-research/locomo/blob/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/README.MD
