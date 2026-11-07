# Installed v1 acceptance and evidence matrix: published rc.16

Status: **reconciled evidence baseline; remaining acceptance open**.
Owner/product/platform/release decision maker: Joshua Myers. Assessed 2026-11-07;
review by 2026-11-12 or before stable approval. This is the installed-CLI adaptation
of the production template's integration/E2E plan, not execution authority.
See the [current readiness assessment](V1_PRODUCTION_READINESS_RC16.md) for findings
and the [historical assessment](V1_PRODUCTION_READINESS_RC14.md) for dated context.

## Frozen identities, dependencies and fidelity

| Bundle | Artifact, source, configuration and test binding |
|---|---|
| C16 | Published `v0.1.0-rc.16`, source `14eb79d52950f340aba159815222e04e6ea864e3`, release 437243456, epoch 2. Four enrolled signed archive descriptors in public `release.json`, SHA256 `1882d3db109ebc3b6f0d5c84de8dec0eecde96a47da5f72ad444d133b30ea3bc`; actual per-platform digests/sizes and all report hashes are bound by the [qualification review](RC16_QUALIFICATION_REVIEW.md) and [public inventory](RC16_PUBLICATION_WORK_NOTE.md). Native tools and controller revisions are separately identified in the qualification record; the runtime source stays frozen. Host Python/Node absent for standalone smoke. |
| C14-L | Signed macOS arm64 rc.14 executable SHA256 `9f2651de14244fd0d46bf620b35797118c83d1a9ab3315e8d3790e2b4c931405`, source `ec3211e23c4a3e2b20837114e707bc8ebcbe625a`, worker image `sha256:a0e21a0c251972e3e87f05a6406269f1804c6e879863d6598e2f6326c67f5c9a`. Exact native executable/context, configuration/controller and test identities are retained in [rc.14 review/work note](RC14_QUALIFICATION_REVIEW.md); they are not rebound to C16. |
| Live configuration | Codex 0.163.0, Claude Code 2.1.283; Sol/medium chat, creator and child; Terra/medium and Sonnet 5/high critics; Astra/medium judge. Native tool-free/no-memory mode, bounded `--plain --json --no-memory` selection; 120s native deadline, 155s outer role timeout, 128,000/16,000 input/output bytes, 8,192 reported output tokens, zero correction/retry/response repair, 600s coding wall, 14 calls/store and 28 total ceiling. Each actual immutable authorization remains bound to its original run. |
| Source reuse | C15→C16: only `app_release.py` changes among 418 runtime Python files; the other 417, runtime export, Dockerfile and both subscription adapters are identical. C14→C15 setup diagnostics remain historical. Source identity supports reuse of unchanged contracts, not fresh artifact/native-client execution. Controller sources and failed/successful jobs are separately bound in the rc.16 review. |
| Substitute boundaries | C16 offline UI/diff/recovery and native diagnostic cases use controlled fixtures/fake native clients where declared. Source ModelReview rejection corpus is source evidence. Actual C14-L native subscription calls, container integration/fresh tests and C16 actual predecessor binaries/public downloads are real within their recorded scopes. Development cask layouts and ordinary Linux CI are substitutes for neither Apple quarantine/notarization nor Windows-hosted WSL2. |

No exact C16 live execution is claimed. Reuse of C14-L is accepted historical
corroboration of unchanged paths; a stable equivalence decision is still for the
owner, with source/config/test/artifact differences reviewed. Other OS native
client authentication, host process/pipe behavior, filesystem ownership and worker
containment require their own boundary evidence. Do not create a full Cartesian
product of lower-level permutations or repeat paid calls without a distinct risk.

## Requirement and evidence register

“Passed” always names a scope. “Open” means direct acceptance has not been located
or established, not that implementation is absent. Every open row is owned by
Joshua Myers with checkpoint 2026-11-12; no risk exception is accepted here.

| Case / plan boundary | Actual admitted outcome and lane | Open work / required acceptance |
|---|---|---|
| M01 / §§28–29 signed distribution | **Passed C16**: macOS arm64/x86_64 and Linux arm64/x86_64 signed install; all 418 source identities per archive; 62 reports/80 assets; useful SBOM and invalid inventory controls. Fresh unauthenticated public macOS arm64 install/version/setup and all public bytes verified. `tools/qualify_installed_candidate.py`, `tools/release_sbom.py`, `tests/test_release_sbom.py`. | Other-platform public consumer smoke is not newly claimed. Changes to runtime packaging, signature, interpreter or published inventory invalidate the affected direct checks. No reason to rerun unchanged C16 evidence simply to close this assessment. |
| M02 / §§16.4, 17.1, 28 offline installed behavior | **Passed C16, four targets, both files/snapshot and SQLite**: cold resume, terminal/diff behavior and recovery; six native diagnostic cases/target; 48 actual predecessor journeys across rc.1/2/3/5/7/9/10/11/12/13/14/15, including rc.7 cross-epoch refusal before state/pointer changes and compatible retained backups. Actual generated formula on two Macs. `tools/qualify_published_upgrade.py`, `tests/test_app_distribution.py`, diff/recovery tests. | Offline fixtures do not establish real provider, actual interactive terminal combinations, real two-user egress or complete newer-version guided update/restart. Fresh candidate changes rerun only affected row boundaries plus required release gates. |
| M03 / §16.0 chat, steering, cold resume | **Passed C14-L**, macOS arm64, both stores: real subscription chat/steering/context/cold resume, explicit same-owner continuation. No C16 live run. | Owner reviews C14→C16 equivalence and exact stable client/profile. Actual missing OS/native-auth/host containment must be qualified with freshly pinned readiness and bounded authority; a shared Python controller alone does not cover them. |
| M04 / §§16.0, 16.4 coding → review → approval → integration | **Passed C14-L**, both stores: plan and implementation critics/judges, all 12 subject-bound ModelReviews, exact creator approvals before integration, source-only integration and three fresh integrated tests/store, zero failures/errors/skips. Eight coding workers absent. | Preserve original harness failure and separately authorized SQLite run. No generic `/review`, successful repository `/inspect`, arbitrary task/model or memory-enabled coverage is inferred from panel ModelReviews. Review exact missing advertised profiles before new calls. |
| M05 / §16.0.2 memory, inspection and independent direct review | Source/fixture and narrower existing feature records corroborate implementation. C14-L uses no-memory/tool-free native mode; `/inspect` refusal is evidence of refusal, not successful inspection. Credential attachment remains inactive by default under its own gates. | Reconcile each advertised enabled-memory and allowed contained-tool/repository-inspection/direct-review journey against existing feature evidence. For any actual missing boundary, use synthetic curated facts/repo, approved tool allowlist and fresh sessions; verify bounded context, reviewer independence, exact approval and resulting durable state. Do not activate credential attachment to fill an unrelated matrix row. |
| M06 / §27.1 real Windows-hosted WSL2 | Preparation runbook and actual older narrowly scoped §31.7 read-only review exist. Ordinary Linux signed/offline results are useful Linux evidence. | General installed WSL2 acceptance needs actual host build/WSL2 distro/kernel/mount/native Linux clients, Docker/containment identity, non-root user and ext4 private roots; signed candidate public entry points, required workflows and teardown. Narrow old read-review checks do not qualify the whole product. Native Windows remains v0.1.1. |
| M07 / §§17.2–17.4 real-principal privacy/egress | Existing ownership/memory/SQLite/recovery source and fixtures reject synthetic foreign identity; local private/hash checks pass their scopes. | Two actual OS principals for each supported backend: read/write/list/search/resume/replay/export/delete, reference substitution/cache reuse, forged IDs and model-selection isolation, concurrent same-owner access, fresh-session isolation, migration failures, rotation and owner-scoped reset. Outbound capture must show no unintended analytics/storage. Use synthetic sentinels; do not open evaluation stores or real private histories. |
| M08 / §§16–17 terminal/redaction/recovery composition | C16 offline terminal/diff/recovery plus feature-level diff acceptance and memory backup/discard records cover their declared cases. C14-L cancellation/uncertain-refusal and worker teardown are direct. | Reconcile supported ordinary interactive terminal/tmux choices and versioned redaction at log/index/replay/export/notification boundaries. Cover required concurrent/varied-order/cancellation cases with synthetic fixtures; disclose physical deletion/backup delays. Do not equate updater backup with disaster recovery or source PTY fixtures with all real terminals. |
| M09 / §28 public discovery/notice/upgrade/restart | **Corrected discovery passes C16**: four actual signed native old-refusal/explicit-upgrade/public-read journeys; after publication, fresh macOS arm64 online install and separate actual public rc.15→16 explicit rollout preserve synthetic state/cache, then authenticate public rc.16 without pointer changes. Old client cap failure remains immutable history. | R16-01: same-version lookup is not a newer-version notice or confirmed guided upgrade/restart. Real grant/ledger and exact future-public-pair lifecycle acceptance remains open, with fresh scoped authority where needed. |
| M10 / §§29–29.4 public manager/cask lifecycle | Fresh public npm dist-tags `{"latest": "0.0.0-stage", "preview": "0.1.0-rc.1"}`, formula versions `["0.1.0-rc.2"]`, cask paths `[]`. C16 generated-formula journeys pass on two Macs; that is not current public-manager publication. | Current reviewed manager release plus real public install, predecessor upgrade, origin/conflict, restart and uninstall; Apple custody/notarization/quarantine and default-tap gates remain separately owned. |
| M11 / release checklist operations/restore/governance | Protected immutable release, pinned workflows, required checks/gitleaks and bounded diagnostics are direct evidence. Current host controls and narrow updater backups are disclosed in assessment. | R16-04–08: accepted operations/latency/support/budget and synthetic restore evidence, host-control exceptions/changes and license/native-version disposition. None is silently accepted by the matrix author. |

## Execution handoff for remaining cases

Use the existing [installed qualifier](../tools/qualify_installed_candidate.py),
[actual predecessor qualifier](../tools/qualify_published_upgrade.py),
[WSL2 runbook](WSL2_QUALIFICATION.md), [cask runbook](MACOS_CASK.md),
[diff acceptance](CONVERSATION_DIFF_ACCEPTANCE_VERIFICATION.md) and
[memory backup/discard](CONVERSATION_MEMORY_BACKUP_DISCARD.md) as case-specific
starting points. Do not run example placeholders as qualified commands.

Before any missing-case execution, freeze a case packet containing:

- Exact source, signed archive/executable digest, installed version/epoch, lock and
  runtime export, test/controller revision and worker image digest. Verify public
  enrolled metadata and readiness before launch; preparation alone grants no calls.
- Host/architecture/OS, client executable/context identity and selected route,
  model/effort, backend, memory/inspection/tool policy and actual versus substitute
  dependencies. Do not dump environment variables, auth caches or native transcripts.
- Synthetic per-case private HOME/state/repository and worker namespace, declared
  seed/order/concurrency, principal identities by safe labels, permissions and
  bounded readiness deadline. Preserve current private roots and all old ledgers.
- Expected positive and refusal outcomes, durable-state/hash assertions, before-send
  authorization and finite per-call/global walls and byte/call caps where live.
  Fresh owner authority must name the exact missing live scope and costs. No silent
  retry, replacement scope, renewal or response repair after a first unplanned failure.
- Allowlisted event/reason receipts with source/config/test/artifact hashes,
  actual counts/skips, original first failure, cleanup and worker absence. Keep
  raw engineering records private under their declared retention policy; tracked
  records contain sanitized conclusions and hashes. Do not create sampling artifacts.

For M07 first build a provider-free synthetic two-principal walking skeleton,
with fail-closed cross-owner substitutions and ordinary outbound capture. Validate
positive same-owner resume/concurrency and negative cross-owner operations on both
backends before any dependent external profile. For M09 retain corrected public discovery and qualify a genuine future newer-public
version lifecycle when available; do not fabricate a public successor.
For M03–06 reuse already proven internal permutations; execute only missing real
OS/auth/containment/profile boundaries after owner review and appropriate authority.

Required success/rejection/recovery assertions, lease/TTL and teardown apply even
if launch, readiness or cleanup fails. Classify product, harness and infrastructure
failures separately; none becomes a pass through retry. A missing/skipped/timed-out
required case blocks its lane. Any quarantine or exception needs exact revision,
owner, rationale, compensating evidence and expiry. No universal sample-count,
automatic diagnostic rerun or assumed independence is introduced.

## Delivery lanes and ownership

| Lane | Current command/evidence | Remaining decision / exit |
|---|---|---|
| PR source and wheel | `make check`, required quality/container/gitleaks/four native standalone checks; protected audit | Keep required checks fail-closed. Calibrate queue/setup/execution and triage budgets from actual runs; no invented feedback percentile. |
| Signed candidate | Protected release workflow, actual installed/predecessor/diagnostic/SBOM admission | Corrected discovery, publication and affected four-target evidence pass. Future newer-version guided lifecycle remains R16-01; preserve all immutable releases. |
| Native subscription | C14-L bounded actual both-store campaign; no automatic scheduled inference | Owner equivalence decision and scoped fresh authority for missing real boundaries; first failure and uncertain holds remain visible. |
| General WSL2 / privacy / managers | Named runbooks and source contracts, partial target evidence | Actual host/principals/public route, synthetic fixtures, readiness/cancellation/cleanup and configuration/test identities. |
| Operations and accountable handoff | R16-04–08 register | Owner accepts support window, budget, maintenance/review cadence, RPO/RTO, representative reliability denominator, license decisions and legitimate exceptions. Independent reproduction or an explicit solo-owner exception remains open. |

Discovery/reconciliation is complete. Harness expansion, missing integration/E2E,
representative reliability observation and enforcement/handoff remain owned phases,
not work silently declared complete by this document. There is no accepted launch
schedule, staffing commitment, numeric reliability target or stable approval.
