# V1 readiness reconciled against published rc.15

**Reconciliation complete; stable conversational v1 remains blocked.**
Published rc.15 is the owner-accepted macOS/Linux standalone preview. Its useful
SBOM and fail-closed completeness checks resolve R14-01 for this release. This
assessment preserves the [dated rc.14 assessment](V1_PRODUCTION_READINESS_RC14.md)
and replaces its operative work list. It does not turn rc.14 live results into
fresh rc.15 live qualification or constitute a stable-release approval.

Assessed 2026-11-05 UTC. Accountable owner: Joshua Myers. Operator: Codex.
Next review checkpoint: 2026-11-12, before stable approval, or after invalidating
changes. This checkpoint is proposed review timing, not a promised release date.

## Authority and method

Product requirements remain [plan §§16–17](mos-eisley-plan.md#16-cli-interface),
[WSL2 §27.1](mos-eisley-plan.md#271-version-010--supported-wsl2-deployment),
[updates §28](mos-eisley-plan.md#28-application-update-notifications-and-guided-upgrades)
and [installation §29](mos-eisley-plan.md#29-codex-style-installation-and-first-launch).
Mos's adopted production guidance remains pinned at
`8879be48f3b760e65f6bed32f8740314fe92910d`; see the
[adoption survey](PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md).
The comparison uses upstream production-project-template
`351610f91e91710a63316b631ff0d61a6c997458`, its
[release checklist](https://github.com/joshuamyers22/production-project-template/blob/351610f91e91710a63316b631ff0d61a6c997458/checklists/RELEASE_READINESS.md),
[integration/E2E guide](https://github.com/joshuamyers22/production-project-template/blob/351610f91e91710a63316b631ff0d61a6c997458/docs/INTEGRATION_AND_E2E_TESTING_GUIDE.md)
and [planning template](https://github.com/joshuamyers22/production-project-template/blob/351610f91e91710a63316b631ff0d61a6c997458/templates/INTEGRATION_AND_E2E_TESTING_PLAN.md).
Comparison recommendations do not silently become repository policy. The unrelated
dirty template checkout was left untouched; generic staffing, sample counts and
schedule defaults are not imposed on this local CLI.

Two evidence passes reconcile retained qualification/source differences, then
fresh public distribution, dependency audit and governance observations. The
[work note](RC15_V1_READINESS_WORK_NOTE.md) records verification and errors.
The [installed acceptance matrix](V1_INSTALLED_ACCEPTANCE_RC15.md) freezes the
actual evidence scopes, configuration/test references, reuse rules and missing
real-boundary cases. No provider call, new grant, key inspection, runtime release,
security-setting change or study was performed. Restricted evaluation stores were
not accessed; engineering receipts confer no evaluation eligibility.

## Exact release and admitted evidence

| ID | Evidence and limit |
|---|---|
| E15-1 | [Published immutable rc.15](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.15), release `435339429`, published `2026-11-05T14:55:24Z`; frozen source `21fc2b02db5611d806626ad8c70698b3c7181577`, annotated tag `ac6627da26ce8ab1488197fbd525fe7f7def93e7`, storage epoch 2. [Protected run 41948231550](https://github.com/joshuamyers22/mos-eisley/actions/runs/41948231550), attempt 1, succeeded. |
| E15-2 | [Signed qualification review](RC15_QUALIFICATION_REVIEW.md): 58 reports / 76 assets, four signed installations and both-store offline matrices, 44 actual predecessor journeys on four macOS/Linux targets, including actual rc.14 upgrades and rc.7 downgrade refusal; four diagnostic matrices and two generated-formula journeys. All 418 runtime Python files match frozen source in each archive. No inference. |
| E15-3 | Same review: CycloneDX 1.6 inventory with 6,485 components / 6,486 dependency records, actual wheel/sdist, all four applications/bootstrap packages, interpreter and file identities. Canonical/schema/coverage checks, independent marker/reader comparisons and malformed-BOM controls pass before publication admission. Unknown native versions remain hashed-file identities; host OS/external clients are excluded. License inventory is not legal clearance. |
| E15-4 | [Owner publication/public verification](RC15_PUBLICATION_WORK_NOTE.md): all 76 unauthenticated public downloads match qualified names, sizes and SHA256; immutable attestation and enrolled metadata/four archive hashes verify. Reconstructed public tree passes canonical admission. Fresh public macOS arm64 installation/version/credential-free setup passes, CPython 3.12.14 and all 418 source files match. No other-platform public consumer or live claim. |
| E15-5 | Actual protected `make check audit`: 3,948 source tests, 17 skips, 86% coverage; 2,916 wheel tests, 13 skips; audit clean for 54 runtime packages. Source PR #363 and evidence PR #364 merged normally after 21 and 14 checks. Publication docs #365 merged normally after all 14 checks on 2026-11-05. These are retained passing gates, separate from this documentation branch's checks. |
| E14-L | [Historical rc.14 review](RC14_QUALIFICATION_REVIEW.md): actual signed macOS arm64, files/snapshot and separately authorized SQLite, chat/steering/context/cold resume, coding plan/implementation critics and judges, exact creator approvals, integration and three fresh tests per store; all 12 ModelReviews bind their subjects, eight workers removed. 28 dispatches / 26 completions include two planned uncertain cancellations. Original controller exit 1 at RC14-HARNESS-01 stays visible; its correction and separately authorized SQLite refusal are separately recorded. |
| E15-6 | Fresh public observation at 17:58 UTC: release identity/immutable flags and all 76 API asset names/sizes/digests still match retained public inventory. npm `@mos-eisley/mos-eisley` preview is rc.1; public formula is rc.2; no cask. Public SBOM freshly downloaded again: 5,100,313 bytes, original SHA256, same counts. |
| E15-7 | Fresh pinned uv 0.13.4 locked/no-dev audit: exit 0, no known vulnerabilities or adverse project statuses in 54 runtime packages. This does not establish native-library vulnerability completeness or license suitability. |
| E15-8 | Fresh real preview discovery fails `ReleaseError: download exceeds byte limit`. The public ten-release feed is 914,579 bytes against `MAX_METADATA=131072`. Replaying those public bytes offline through the unchanged production downloader reproduces the same refusal. No application cache, installed root or provider was touched. |

The historical live profile is Codex 0.163.0 / Claude Code 2.1.283, Sol/medium
chat/creator/child, Terra/medium and Sonnet 5/high critics, Astra/medium judge;
no-memory, tool-free native profile. Explicit fresh grants selected 120 seconds,
128,000 input bytes, 16,000 output bytes and 8,192 reported output tokens.
Four Claude critic observations were 38.285/40.511 seconds for snapshot and
36.338/34.664 for SQLite. They establish successful bounded examples, not p95/p99,
a success-rate estimate, billing guarantees or coverage of every product profile.

## Production-template gates

| Gate | Reconciled status / closure needed |
|---|---|
| Critical journeys, failure and cancellation | Passed for E15-2's offline targets and E14-L's exact historical live profile; partial for full v1. Matrix M03–M08 identifies remaining profile/OS/privacy acceptance. |
| Locked/audited/licensed dependencies | Lock/export and current Python audit pass; useful SBOM defect closed. Owner disposition of license suitability and unknown native versions remains open, R15-08. |
| Version/source/artifact/SBOM traceability | Passed for E15-1–4, including public bytes. rc.14's original empty BOM remains immutable history. |
| Secrets/private content | Existing history-aware gitleaks and bounded diagnostic tests pass for their scope. Full real-principal/egress acceptance remains open; no assertion that all privacy boundaries were qualified. |
| Compatibility, migration, rollback and recovery | E15-2 passes actual predecessor and cross-epoch refusal scope. General disaster recovery and private-state restore objectives remain open, R15-05. |
| Operations, capacity and latency | Bounded diagnostics/call deadlines exist. Owned whole-product SLIs/SLOs, support window, representative load/latency/overload and independent health/loss evidence remain open, R15-04. |
| Owned risks and accountable decision | Owner and review checkpoint recorded below. No new risk exceptions or whole-product stable acceptance have been approved. |

## Findings and disposition

All open rows have accountable owner **Joshua Myers**, review checkpoint
**2026-11-12 or before stable approval**, and no accepted exception/expiry yet.
P1 means stable blocked until evidence or an explicit legitimate scoped disposition;
P2 means process/documentation debt. An evidence gap is not an asserted exploit,
license violation or absence of implementation.

| ID / priority | Disposition and acceptance evidence |
|---|---|
| R14-01 / closed for rc.15 | Useful generated SBOM and fail-closed completeness admission are qualified and publicly verified, E15-3/4/6. Do not reopen this as the next engineering task. Residual license/native-version limits are tracked separately as R15-08. |
| R15-01 / P1, new confirmed defect | Preview discovery fails before version selection because the real GitHub feed exceeds its cap, E15-8. `app_release.release_metadata` is unchanged from rc.14; `app_update.check_notice` marks discovery failed/backoffs, while explicit standalone `update` depends on the same fetch. Actual full CLI notice/restart behavior was not executed here. Fix bounded discovery in a new candidate, keep signed metadata and endpoint/deadline limits, prove oversized inventory/refusal/selection offline, then qualify an actual installed predecessor → new public release with state preservation and restart. Matrix M09. |
| R15-02 / P1, carries R14-02 and R14-04 | The matrix is now reconciled; missing direct full-v1 evidence remains for other native OS/auth/containment boundaries, actual Windows-hosted general WSL2, memory/inspection/direct-review profiles and two-real-principal privacy/egress acceptance. Preserve E14-L and justify narrower reuse; do not claim fresh rc.15 inference or silently shrink the product. Matrix M03–M08. |
| R15-03 / P1, carries R14-03 | Current public npm/formula routes lag; no cask. Generated-formula qualification is not current public-manager publication. Developer ID/notary custody and real quarantined Homebrew lifecycle remain prerequisites in the [cask runbook](MACOS_CASK.md). Owner provisions custody outside chat/Git; future candidate must admit actual signed/notarized packages and public clean/upgrade/origin/conflict/uninstall checks. Matrix M10. |
| R15-04 / P1, carries R14-05 | Establish accepted CLI SLIs/SLOs, content-free versioned telemetry and independent health/loss signals, representative workload/denominator, p50/p95 and overload/dependency-failure evidence, support/triage/escalation owner and operating budget. [Plan §17.5](mos-eisley-plan.md#175-operational-logging-and-evidence-driven-improvement) remains planned integration; a cloud observability stack is not required. |
| R15-05 / P1, carries R14-06 | Owner-controlled signing-custody backup/restore and synthetic private-state/ledger restore drill need accepted RPO/RTO, permissions/rotation and compatible forward recovery. Updater backup/downgrade refusal is narrower. Never inspect/export private keys or restore over active ledgers for assessment. |
| R15-06 / P1 owner disposition, carries R14-07 | Fresh host settings: all Actions allowed, SHA pin enforcement off; GitHub-native secret scanning/push protection, automated security updates and private vulnerability reporting disabled; main checks not strict/up-to-date and commit signatures not required. Existing pinned workflows/gitleaks and protected no-bypass releases are compensating evidence, not server enforcement. Owner selects controls or dated justified exceptions. Vulnerability-alert endpoint 404 remains unverified, not proof disabled. No settings changed. |
| R15-07 / P2, carries R14-08 | Three merge methods allowed, branch auto-delete off, zero required approvals under disclosed solo-owner arrangement. Align >=85% project-brief target with enforced 84%, or record an owner decision; actual candidate achieved 86%. Review history-preserving merge/retention policy and contributor signing capability without silently changing settings or revoking passed checks. |
| R15-08 / P1 residual supply-chain review | Inventory includes declared license files/metadata and honest native file identities. Record actual third-party license suitability/obligations, treatment of unknown native versions and external-client/OS exclusions, owner acceptance and maintenance cadence. A clean Python audit or inventory count cannot close this review alone. |
| R14-09 / documentation corrected | Current README/publication pointers credit rc.15 and distinguish rc.14 live evidence. Latency guidance now records the successful historical post-fix profile. Historical rc.14 assessment/work note remain byte-identical; September record retains dated findings with a current pointer. |

## Ordered next work and decision boundary

1. **Fix R15-01 preview discovery in a new candidate.** This is the smallest
   confirmed unpaid product defect. The fixture is the bounded public feed and
   its digest below; retain the first failure. Do not merely remove limits or
   treat a mocked tiny feed as public acceptance. No native call is needed.
2. Owner reviews [matrix M03–M10](V1_INSTALLED_ACCEPTANCE_RC15.md), freezes the
   advertised stable profile and accepts explicit equivalence or missing cases.
   Prepare synthetic two-principal and real WSL2 environments; obtain fresh
   case-specific native authority only where actual external evidence is needed.
3. Advance manager/cask custody, license disposition, operations and restore tracks
   independently. Each gate needs actual target evidence and accountable acceptance.
4. Cut/sign a new immutable candidate after the discovery change, rerun affected
   signed/offline/public update checks and only invalidated live scopes. Review all
   remaining gates before deciding exact stable artifact/support scope.

Files/SQLite are the shipped first backend scope. Native Windows 0.1.1,
post-Windows embedded terminals, PostgreSQL/S3 and later §31 automation are outside
this gate. G3/G5/G6 studies/learned routing remain deferred under
[ADR-0011](adr/0011-defer-studies-until-production.md); no comparative study is
invented as a prerequisite. This assessment grants no provider retries, study,
policy activation, stable date/budget or stable publication authority.

## Evidence bindings

Original qualification/publication hashes and private receipt locations are in
E15-2/4. Public `release.json` SHA256:
`a7dc636d2dc1c6078694393dd27388b5fea53cbe9bb3d2bbe61d9a18e646915b`.
Public SBOM SHA256:
`a86e8daa7c86b3436a27b8b58b40c1cbe8792050bd69bd2704c4e39f3ea4a3b1`.
Public-feed reproduction SHA256:
`eb760c6de4f02df7783e7e37c3217a7e5e6b4a7644cd21b6a72961ea5bfa09bb`.
Ignored `.work/remote-observation.json`, `governance-observation.json`,
`public-feed-diagnostic.json`, `source-equivalence.json` and audit/validation
records bind the fresh observations; their hashes are in the work note.

Completion of reconciliation records **block stable v1; retain accepted rc.15
preview status**. Security/governance exceptions and stable release require
accountable owner review beyond this agent's assessment.
