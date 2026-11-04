# V1 production-readiness assessment: published rc.14

**Assessment complete; full conversational v1 / stable 0.1.0 remains blocked.**
Published rc.14 is an owner-accepted, qualified macOS/Linux standalone preview.
Its four-target signed distribution and both-store installed live workflow are
complete within the scopes below. This assessment credits those results; it does
not reopen their campaigns or retroactively approve a stable launch.

Assessed 2026-11-04 UTC. Accountable owner: Joshua Myers. Operator: Codex.
Re-review by 2026-11-11, before a stable decision, or after an invalidating change.
The date is an assessment checkpoint, not an owner-accepted delivery commitment.

## Candidate, requirements and method

- Published source: `ec3211e23c4a3e2b20837114e707bc8ebcbe625a`, incorporating
  `11fe46514e7962731023538fc50789c8b9d7fd45` and its locked dependency set.
- Tag `v0.1.0-rc.14`; annotated object
  `f6cf41ac138dd3b1020864510ca4b21440bdae53`; storage epoch 2.
- Immutable prerelease [434439039](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.14),
  published 2026-11-04T20:50:38Z. [Protected run 41699667393](https://github.com/joshuamyers22/mos-eisley/actions/runs/41699667393)
  attempt 1 completed successfully, including all four signed qualification jobs.
- Product authority: [plan §§16–17](mos-eisley-plan.md#16-cli-interface),
  [WSL2 §27.1](mos-eisley-plan.md#271-version-010--supported-wsl2-deployment),
  [updates §28](mos-eisley-plan.md#28-application-update-notifications-and-guided-upgrades),
  [installation/cask §§29–29.4](mos-eisley-plan.md#29-codex-style-installation-and-first-launch),
  and [release checklist](../checklists/RELEASE_READINESS.md).
- Applied Mos's adopted [template guidance](PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md)
  at `8879be48f3b760e65f6bed32f8740314fe92910d`, plus the fresh upstream-main
  [release checklist](https://github.com/joshuamyers22/production-project-template/blob/351610f91e91710a63316b631ff0d61a6c997458/checklists/RELEASE_READINESS.md),
  [integration/E2E guide](https://github.com/joshuamyers22/production-project-template/blob/351610f91e91710a63316b631ff0d61a6c997458/docs/INTEGRATION_AND_E2E_TESTING_GUIDE.md)
  and [planning template](https://github.com/joshuamyers22/production-project-template/blob/351610f91e91710a63316b631ff0d61a6c997458/templates/INTEGRATION_AND_E2E_TESTING_PLAN.md)
  at `351610f91e91710a63316b631ff0d61a6c997458` (upstream main observed directly).
  Unrelated local template edits were untouched. Template additions are assessed
  explicitly; this task does not silently change repository policy.

Two evidence-changing passes traced requirements/source/tests and retained exact
qualification, then checked fresh public release/package/governance observations
and contradictions. A focused current dependency audit and public SBOM inspection
added evidence. The [work note](RC14_V1_READINESS_WORK_NOTE.md) records bounds and
verification. No new inference, grant, publication, raw credential/key inspection,
study, sampling-registry, custodian, label-store or outcome-store access occurred.
No full runtime qualification was repeated for a documentation assessment.

Statuses mean **passed for stated scope**, **partial**, **open**, or **deferred
outside this release**. Source/fixture coverage, installed offline checks, actual
live evidence and accountable acceptance are separate. Missing evidence is not a
claim that an implementation is absent or that an exploit occurred.

## Admitted evidence

| ID | Direct evidence and actual scope |
|---|---|
| E1 | [Qualification review](RC14_QUALIFICATION_REVIEW.md): 54 reports and 71 prepared assets; signed installation, both-store installed matrices and expanded offline native diagnostics on macOS/Linux arm64/x86_64; 40 actual predecessor journeys, including rc.13 upgrades and rc.7 cross-epoch refusal; two generated-formula journeys. |
| E2 | Same review, combined installed macOS arm64 live reconstruction: snapshot plus separately owner-authorized SQLite; chat/steering/context/cold resume, plan/implementation critics and judges, exact creator approvals before integration, source-only integration, three fresh integrated tests per store with no failures/errors/skips, and eight removed coding workers. |
| E3 | 28 dispatches, 26 native completions and two deliberately cancelled uncertain slots; refusal to resume without replay. Original controller exit 1 at RC14-HARNESS-01 remains preserved; its exact read-only diagnosis/offline correction and successful SQLite refusal establish the product boundary. All nine older roots and original rc.14 root remain unchanged. |
| E4 | [Owner/publication record](RC14_PUBLICATION_WORK_NOTE.md): evidence PR #360 merged normally after all 13 checks; owner-approved protected publication; immutable attestation and all 71 unauthenticated public downloads match. All four archives verify against enrolled metadata. Fresh public macOS arm64 bootstrap/version/setup passes with no host Python/Node on child PATH; all 418 runtime Python files match source. |
| E5 | Frozen combined `make check`: 3,929 source tests, 17 skips, 86% branch-inclusive coverage; 2,916 installed-wheel tests, 13 skips; lint/format/types/export/build passed. Protected preparation additionally passed audit and container gates. Counts/skips retain original attribution; this is not a new gate run. |
| E6 | Fresh read-only observation at 21:03 UTC: immutable release/source/tag and all 71 API asset identities match retained qualification; all 11 release jobs succeeded. npm `preview` is rc.1; the public formula is rc.2; tap tree has a formula and no cask. PR #361 is still open with auto-merge enabled at observation time. |
| E7 | Fresh `uv audit --preview-features audit-command --locked --no-dev`: exit 0, no known vulnerabilities or adverse project statuses in 54 runtime packages. This is vulnerability evidence, not license or SBOM-completeness review. |
| E8 | Fresh public SBOM: 402 bytes, SHA256 `bb941dfdc7f9cfec7d94afc868cdb3c0a1bef4682b1c6ab4d0fcd6369cc6cb6c`; JSON declares CycloneDX 1.7, but has no `components` or dependency graph. Only metadata identifies a file named `./dist`. JSON decoding is not schema/coverage validation. |
| E9 | Current macOS arm64 public executable: `codesign -dv --verbose=2` reports ad-hoc signature and no TeamIdentifier. This is distinct from the passing enrolled Ed25519 release signature. No notarization/quarantine execution is claimed by this read-only inspection. |
| E10 | Fresh repository controls: administrator-enforced PR/check/conversation protection, no force pushes/deletion; immutable `v*` tag rules with no bypass; protected release reviewers and no administrator bypass; Actions token read-only and cannot approve PRs. Additional current-template differences are recorded below. |

The actual live profile uses Codex 0.163.0 and Claude Code 2.1.283; Sol/medium
chat/creator/child, `gpt-5.6-terra`/medium and Sonnet 5/high critics, Astra/medium
judge. Its fresh grants enforce 120 seconds, 128,000 canonical input bytes,
16,000 text output bytes and 8,192 reported output tokens. The four Claude critic
calls completed in 38.285/40.511 seconds (snapshot) and 36.338/34.664 seconds
(SQLite), with valid results and EOF. These four observations do not establish
p95/p99 or a general success-rate guarantee. Native billing/internal retries remain
unverified. Defaults and every old grant stay unchanged.

## Installed acceptance matrix and evidence equivalence

| Target | Signed install, upgrades, both-store offline UI/diff/recovery/diagnostics | Actual subscription workflow | Remaining finished-product evidence |
|---|---|---|---|
| macOS arm64 | Passed E1; public bootstrap passed E4 | Passed E2–E3, both stores | Freeze the full advertised profile; reconcile memory-enabled, repository-inspection/direct-review and ordinary interactive journeys with their own evidence/authority |
| macOS x86_64 | Passed E1, including generated formula | Not observed in this campaign | Native-client/profile coverage or a reviewed, justified equivalence decision; actual current package-manager journeys |
| Linux x86_64 | Passed E1 | Not observed in this campaign | Actual Linux native-client/profile qualification, installed launch/authentication and supported execution boundary |
| Linux arm64 | Passed E1 | Not observed in this campaign | Architecture/native-client coverage or justified equivalence; actual advertised manager journeys |
| Windows-hosted WSL2 | General §27.1 qualification remains open | Not supplied for rc.14 | Actual Windows/WSL host provenance, Linux filesystem, installed artifact, credential/terminal/containment/upgrade matrix; older focused read-review evidence is narrower |

The live harness deliberately used `--plain --json --no-memory`; `/inspect`
refusal without dispatch was tested, not successful repository inspection.
The coding panel's ModelReview validation is not blanket qualification of every
other `/review` roster, target or approval path. Those are scope statements,
not deductions that the successful campaign failed.

All four installed offline matrices already exercise the real signed CLI and
terminal/diff/recovery boundaries. Source/wheel suites provide additional
memory/workspace, owner, rendering and request-guard coverage, including
[common renderer uncertainty projection](../tests/test_conversation_recovery.py).
The renderer has no separate execution authority. Reuse of such evidence is
appropriate only with an explicit source/configuration/test equivalence decision;
do not multiply paid calls merely to repeat lower-level permutations. No
unobserved OS, native-client authentication or memory/egress boundary is inferred
from a shared controller. Any new live execution needs its own bounded authority.

## Product and production-template gate matrix

| Gate / requirement | Status and evidence | Remaining acceptance |
|---|---|---|
| Frozen integrated candidate, version/tag/source/provenance | Passed for rc.14, E1/E4/E6; candidate PR #359 merged and tagged source is in main history | A future stable/new candidate needs its own matching version/tag, protected build/sign and affected exact-artifact checks; never change rc.14 assets |
| Core subscription chat, steering, cancellation and cold resume (§16.0) | Passed for E2 profile on both stores | Full launch must name platform/route/capability coverage and explicitly resolve the matrix above |
| Coding, isolated workers, review, creator approval, integration and fresh tests | Passed E2–E3 for bounded pure-Python synthetic task | Do not generalize to arbitrary repositories, languages, tools, provider profiles or new live-review targets |
| Interface and v1 diff (§16.4.1) | Passed scoped historical owner acceptance plus exact rc.14 four-target offline matrices; [diff acceptance](CONVERSATION_DIFF_ACCEPTANCE_VERIFICATION.md), [combined visual review](TERMINAL_INTERFACE_COMBINED_REVIEW.md) | Close any actual gaps identified by the stable capability/UX matrix; source/shared-controller equivalence must be explicit; individual tool streaming is still separately planned |
| Private local snapshot/SQLite, migrations and recovery (§17) | Implemented, regression-covered and installed offline/live evidence E1–E3 | Complete the §17.4 installed two-user/egress/redaction acceptance record; mocked foreign UID/metadata rejection is narrower than two real OS principals |
| Application updates (§28) | Passed scoped signed standalone predecessor/recovery journeys and source regression contracts | Whole advertised surface includes package-manager ownership/migration, new public release reaching old clients, notices/restart and WSL2. Source tests or a generated formula alone do not close those public routes |
| Standalone and pinned/archive installation (§29) | Passed E1/E4 for the stated CLI/bootstrap and archive scope on all four artifact targets; fresh public consumer install on macOS arm64 | Complete clean-machine/route and WSL2 evidence; ordinary browser/quarantined macOS execution is not established by curl installation. Resolve that trust boundary under R14-03, and preserve origin/conflict/uninstall state boundaries |
| npm / Homebrew formula / cask (§29.1, §29.4) | Partial: existing public manager routes are older versions; cask tooling/native development layout exists but production cask is unpublished | Current release-native packages/launcher, public formula lifecycle, Apple signing/notary custody and trust checks, protected cask publication and both native Mac lifecycle/migration checks; default-tap acceptance is a separate explicit plan milestone |
| WSL2 platform (§27.1) | Open; [runbook](WSL2_QUALIFICATION.md) and focused older read-review evidence exist | General installed product qualification on an actual Windows-hosted WSL2 runner; ordinary Linux CI is insufficient |
| Locked dependencies, quality and containers | Passed for stated E5/E7 scope; [Dockerfile](../Dockerfile) pins base digest, stages and non-root UID; actual workers removed | Supply-chain completeness/license record below; future dependency changes invalidate their affected evidence |
| SBOM and dependency-license completeness | **Blocked**, E8/R14-01 | Nonempty, complete-enough runtime/interpreter/native inventory reconciled to released artifacts and locks, with license/notice review and a failing empty/incomplete-BOM gate |
| Security/privacy and credentials | Partial: bounded diagnostics, explicit one-use native authority, owner/path guards and failure tests pass; [threat model](THREAT_MODEL.md) | Cross-user and egress/redaction/replay/export acceptance plus actual advertised credential-store/native-login boundaries; no complete privacy attestation is supplied |
| Operations/support, telemetry, capacity and latency | **Open**: [SECURITY.md](../SECURITY.md) explicitly has no production support SLA; plan §17.5 is planned integration; native failure receipts are narrower | Accepted support/response ownership, content-free event/health contract, operational thresholds/escalation, representative latency/capacity/dependency-failure evidence and maintenance cadence |
| Backup restore/disaster recovery | **Open**: updater rollback, retained backups and epoch refusal pass; [publisher runbook](PUBLISHER_RELEASE_PREPARATION.md) leaves independent key backup/restore to owner | Exercised owner-controlled publisher-key recovery and private-state restore, documented RPO/RTO, access/rotation/loss recovery and preserved ledgers; application rollback is not disaster recovery |
| Repository governance | Partial E10, current-template differences below | Harden or record accepted owned/expiring exceptions; an operator assessment cannot configure or waive them by implication |
| Evidence maintenance and whole-product decision | Partial: fresh review corrects stale entry points; PR #361 still pending at observation | Merge maintained records through required CI; set accepted risk dates and stable scope; accountable whole-product launch decision after blocking gates close |

## Findings, owners and decidable closure

All findings are owned by Joshua Myers for product/risk disposition. Codex can
implement separately authorized engineering slices. Accepted delivery dates and
operating budgets are **not assigned**; decision checkpoint proposed 2026-11-11.
They must be agreed before stable acceptance rather than invented by this report.

| ID / priority | Finding and source | Consequence / smallest closure |
|---|---|---|
| R14-01 / P1 stable blocker | Published SBOM has zero top-level dependency components and no dependency graph (E8). [Release workflow](../.github/workflows/release.yml) scans `dist` before standalone artifacts are downloaded; [publication inventory](../tools/publish_app_release.py) checks bytes, not BOM coverage. Vulnerability auditing passed, but a third-party dependency/license completeness record was not found. | Fix generation and admission in a new candidate. Reconcile installed Python distributions/interpreter/native components and licenses with lock/export/archive contents; reject empty or missing critical-component BOMs offline and in protected publication. Preserve immutable rc.14. This is the next smallest concrete engineering task. |
| R14-02 / P1 stable blocker | Full v1 profile/platform acceptance is not the same as E2's Mac arm64, no-memory, tool-free native profile. General WSL2 is explicitly pending; only narrow older §31.7 read-review evidence exists. | Complete an artifact/config/test-bound integration/E2E record for the advertised v1 matrix. Reuse justified equivalent evidence, then qualify actual remaining OS/native-auth/inspection/memory boundaries. No new calls are authorized here. Scope reduction requires an explicit owner decision. |
| R14-03 / P1 stable blocker | Fresh npm preview is rc.1; public tap formula is rc.2 and no cask exists (E6). [Cask preparation](MACOS_CASK.md) requires different trust and publisher inventory; latest development workflow success is not public qualification. E9 is ad-hoc, not Developer ID. | Qualify current-version manager installs/upgrades/origin/migrations. Owner supplies Apple Developer ID/notary custody through protected channels; integrate both DMGs and records into a future immutable publication, verify default quarantine and real brew lifecycle on arm64/Intel. Review default-tap eligibility/acceptance separately; do not advertise an unavailable command. |
| R14-04 / P1 stable blocker | No full installed §17.4 two-real-user/egress/redaction acceptance record was located. [Memory tests](../tests/test_conversation_memory.py), [SQLite tests](../tests/test_conversation_sqlite.py) and recovery tests reject synthetic foreign ownership, but do not establish every stated boundary on actual principals. | Reconcile existing cases and run only missing real-boundary checks for read/write/list/search/resume/replay/delete/reference substitution, fresh-session memory and outbound destinations. Exercise required redaction/replay/export rules with synthetic sentinels, never real private content. Preserve raw evidence under its declared policy. |
| R14-05 / P1 stable blocker | Whole-product operations/support remain open; [latency profile](CLAUDE_NATIVE_LATENCY_PROFILE.md) supplies bounded call limits, not a representative percentile or overload SLO. [Plan §17.5](mos-eisley-plan.md#175-operational-logging-and-evidence-driven-improvement) explicitly treats general telemetry integration as planned. | Define accepted CLI SLIs/SLOs, content-free versioned events and independent health/loss visibility; test expected/peak/overload/dependency failures and latency distributions with declared workload/denominator. Publish support/triage/escalation ownership and review cadence. A cloud telemetry stack is not a requirement for this local CLI. |
| R14-06 / P1 stable blocker | Protected encrypted signing custody is established, but independent publisher-key backup/restore remains unverified; updater backups do not establish RPO/RTO for private state and ledgers. | Owner-controlled restoration drill using approved custody and synthetic state; measure RPO/RTO, permissions/keys/rotation and compatible forward recovery, with no ledger reset. Never export a key or restore over current private state for assessment. |
| R14-07 / P1 disposition required | Fresh current-template governance comparison: Actions permits all sources and does not enforce SHA pins; GitHub-native secret scanning/push protection, automated security updates and private vulnerability reporting report disabled. Main checks are not strict/up-to-date; required commit signatures are disabled. | Preserve working SHA-pinned workflows and required history-aware gitleaks as compensating controls, but do not label them host enforcement. Owner selects supported controls or records justified, dated exceptions. Verify contributor signing paths before making signed commits blocking. Vulnerability-alert endpoint returned 404; its state remains unverified. No settings were changed. |
| R14-08 / P2 process debt | Automatic merged-branch deletion is off; all three merge methods are allowed. Zero required approvals is the disclosed solo-owner arrangement, not independent review. [PROJECT_BRIEF.md](../PROJECT_BRIEF.md) targets >=85% coverage while [pyproject.toml](../pyproject.toml) enforces 84%; rc.14 actually achieved 86%. | Record the required history-preserving merge exception and branch-retention policy; revisit review controls when eligible reviewers exist. Align coverage target/enforcement or obtain an explicit policy decision. Do not revoke rc.14's passing measured gate or silently alter settings. |
| R14-09 / P2 corrected here | README still called rc.13 current and full live qualification incomplete; latency guidance still called post-fix behavior unverified. Older readiness record described September source. | Update current entry points to rc.14 with exact limits and point to this assessment. Retain older failures/dated assessments as history, and distinguish pending documentation CI from published artifact acceptance. |

The SBOM finding is directly reproduced. The confirmed workflow ordering omits
standalone bundles from the scan input at that point; it does not establish why
the wheel/sdist cataloging also returned no components. Moving a step alone is
not a demonstrated fix: the new gate must verify actual released-component
coverage.

No new exploit, vulnerability or license violation is asserted by an evidence gap.
Conversely, passing an audit or verifying a signed empty BOM does not establish
license completeness, representative reliability or full product readiness.

## Integration/E2E handoff and ordered work

This section applies the upstream planning template to an installed CLI, rather
than copying its proposed staffing, eight-week schedule or numeric reliability
sample defaults as mandatory product requirements.

1. **Supply-chain slice, R14-01.** Implement a useful released-component SBOM and
   fail-closed coverage validation. This is unpaid engineering that can proceed
   independently of Apple custody, WSL access and new native grants. Keep rc.14
   immutable; select a new candidate when artifact/workflow changes are ready.
2. **Freeze and reconcile the v1 evidence matrix, R14-02/R14-04.** Name exact
   platforms, supported routes/models/client versions, memory/inspection/review
   capabilities, retained test revisions, real versus substituted dependencies,
   and evidence-reuse rationale. Real OS principals and host/client boundaries
   need direct evidence. Do not treat each new customer task as a new release
   qualification or authorize additional paid calls by writing this plan.
3. **Close installation/platform tracks, R14-02/R14-03.** Run the general WSL2
   runbook on the actual host and stage current manager packages/casks once their
   custody prerequisites exist. Keep native Windows 0.1.1 and §30 embedded
   terminals outside this v1 gate. Public manager upgrades need actual
   predecessors, origin/conflict handling and state-preserving uninstall.
4. **Establish operability and recovery, R14-05/R14-06.** Agree thresholds,
   support/response ownership, operating budget and RPO/RTO; validate safe telemetry,
   expected/peak/overload and dependency degradation, plus synthetic restore drills.
   No missing quality measurements, probabilities or historical timing is inferred.
5. **Disposition governance and launch, R14-07/R14-08.** Apply owner-approved
   controls/exceptions, collect all required candidate checks, then request an
   accountable whole-product decision for exact stable artifact and support scope.

Existing runbooks provide the walking skeleton: protected release plus
[installed-candidate tool](../tools/qualify_installed_candidate.py), actual
[predecessor qualifier](../tools/qualify_published_upgrade.py), private bounded
live controller and [WSL2 preparation](WSL2_QUALIFICATION.md). They bind source,
artifact/test/configuration hashes, per-run synthetic workspaces, finite deadlines,
worker leases and teardown. Private live receipts and content are not copied into
this report. Public report hashes and sanitized reconstruction are linked instead.

| Lane | Current evidence / gate | Remaining calibrated adoption/handoff |
|---|---|---|
| PR source/wheel/contracts | Existing `make check`; audit and container CI; required `quality`, `container`, `gitleaks` and four native standalone checks | Keep missing/failing required checks blocking; align coverage policy and record feedback/triage budget |
| Tagged signed release | Four real native signed jobs, source-matching artifacts, installed both-store and predecessor matrices | Add semantic BOM completeness and future cask evidence; test missing/empty/tampered artifacts fail admission |
| Native subscription E2E | One bounded campaign split at disclosed harness failure into preserved snapshot and separately authorized SQLite | First-attempt failure stays visible; qualify only invalidated/new scopes with explicit authority; no automatic provider retry/renewal |
| General WSL2/privacy/manager acceptance | Runbooks/source contracts and development fixtures; full target evidence still partial | Pinned host/daemon/client identity, isolated fixtures, readiness/teardown, concurrent/order variation, fault classification and actual public lifecycle |
| Deployment/operations/restore | Public bootstrap verified for rc.14; scoped diagnostic receipts and recovery tests | Owned target-environment smoke/health, monitoring window, representative reliability/latency and restore evidence; independent diagnostic reproduction or a documented solo-owner exception |

A new candidate must identify which changes invalidate which rows. Reusing
rc.14 evidence needs an explicit equivalence decision; version/signing/installer
identities still require their new protected checks. A workflow-only SBOM fix is
not automatic authority to restart native inference. Preserve every first failure,
uncertain hold and cleanup result. Any quarantine/exception needs an owner,
expiry and compensating evidence; no fixed universal retry or sample-count policy
is introduced by the template comparison.

## Explicit deferrals and final decision boundary

PostgreSQL/S3 persistence, native Windows 0.1.1, post-Windows embedded terminals,
and §31 later automation are not silently added to this v1 slice. Files/SQLite
are the shipped first storage scope. G3/G5/G6 comparative studies and automatic
learned routing remain governed by [ADR-0011](adr/0011-defer-studies-until-production.md)
and their own gates; a prelaunch study is not a prerequisite invented to close
functional release acceptance. This assessment grants no study or learned-policy
activation authority and no statistical efficacy claim.

There is no accepted stable release date, operating budget, full risk expiry
schedule or new whole-product approval. The owner may select a narrower product
only by explicitly revising the existing contract. Until blocking gates have
direct evidence or a legitimate scoped disposition, the decision is **block
stable v1; retain rc.14's accepted preview status**.

## Reproducible evidence index

Private sanitized assessment records are in the assessment worktree's ignored
`.work/`; the original candidate receipts stay in the frozen candidate's `.work/`.
Public release/tag/run/registry/tap observations were made read-only. Hashes bind
this assessment to their observations rather than making private records public.

| Record | SHA256 |
|---|---|
| `remote-observation.json` | `fc3d46e43d9c6f0ed5c84b4108c01e9a1df763705f0e6532c81aeb1adf6c8137` |
| `governance-observation.json` | `cb41daad6c23927bcd1c1ea0f387b62cc1b285ddec81167c7364268438df8177` |
| `template-provenance.json` | `d87f9c8224005cb33b997eceb7d742b708acf4cdc9de9f6d973637c52b58e3b8` |
| `dependency-audit.json` | `6c8c8014ff6f7da7aadafe468054b68444a901aeb5f46ea8e11a12e2f5f0876c` |
| Original combined live review | `773eb9dd6eb1d29e40d209a7ae6ada8bcad130ba23724b131d891e2a068ac6a5` |
| Original public inventory review | `18b0464fd1f463fd4e78d5eca273953ad463721289d6713430cd047b950dafde` |
| Original public bootstrap review | `06ffa81d339d352fb857b0db493537fb24940b087ec735f26ff0e26f0ff38e1f` |

Fresh upstream checklist SHA256:
`ffcfb3386d6413dcc7ea5822619719fa84ed924975fc3683f438390077b5d022`.
Source/candidate code, locks, signed assets, grants and historical ledgers were
not changed by this assessment. No independent human security or stable-release
approval is claimed. Remaining risk owners and acceptance work are explicit;
completion of this assessment is separate from completion of the product.
