# V1 readiness reconciled against published rc.16

**Reconciliation complete; stable conversational v1 remains blocked.**
Owner-accepted immutable rc.16 is the current macOS/Linux standalone preview.
R15-01's inventory-limit defect is corrected and publicly verified; useful SBOM
admission remains complete. The [rc.15 assessment](V1_PRODUCTION_READINESS_RC15.md)
and [acceptance matrix](V1_INSTALLED_ACCEPTANCE_RC15.md) remain unchanged historical
snapshots. This document supplies the operative work list, not stable approval.

Assessed 2026-11-07 UTC. Accountable owner: Joshua Myers; operator: Codex.
Next checkpoint: 2026-11-12, before stable approval, or after invalidating changes.
No fresh provider call, new grant, native subscription campaign or study occurred.
Restricted evaluation stores were not accessed; ordinary engineering receipts
confer no evaluation eligibility.

## Authority, production-template method and evidence

The owner requested protected exact-artifact rc.16 publication, public verification
and v1 reconciliation. Product requirements remain plan §§16–17, §27.1 WSL2,
§28 updates and §29 installation. Adopted production-template guidance remains
`8879be48f3b760e65f6bed32f8740314fe92910d`; fresh upstream inspection still finds
`351610f91e91710a63316b631ff0d61a6c997458`. Its
[release checklist](https://github.com/joshuamyers22/production-project-template/blob/351610f91e91710a63316b631ff0d61a6c997458/checklists/RELEASE_READINESS.md),
integration/E2E guide and planning template guide this local-CLI adaptation.
The unrelated dirty template checkout is untouched; comparison recommendations
do not silently change repository policy or impose staffing/sample defaults.

Two evidence passes reconcile retained source/config/test scope, then fresh public
bytes, native consumer entry points, dependency and governance observations.
[Publication record](RC16_PUBLICATION_WORK_NOTE.md),
[qualification review](RC16_STARTUP_QUALIFICATION_REVIEW.md) and the
[current installed matrix](V1_INSTALLED_ACCEPTANCE_RC16.md) bind the actual lanes.

| Evidence | Exact admitted scope and limit |
|---|---|
| E16-1 | [Immutable rc.16](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.16), release `437243456`, published `2026-11-07T01:36:54Z`; source `14eb79d52950f340aba159815222e04e6ea864e3`, annotated tag `cdcb8240b84de4d909d345e35a08654064763535`, epoch 2. Protected recovery run `42324795884`; no rebuild, re-signing or tag retarget. Original run 42102119299 stays cancelled and publisher skipped. |
| E16-2 | Complete 62-report/80-asset reconstruction: four signed installs/both-store offline matrices, 48 actual predecessor journeys including actual rc.15 and rc.7 cross-epoch refusal, four six-case offline diagnostics and two real generated-formula journeys. All 418 runtime sources match in every signed archive. Original Intel 75-minute aggregate timeout and fresh 30-second startup failure remain retained. |
| E16-3 | Bounded startup diagnosis observed 9.699s synthetic predecessor / 12.848s candidate with CPU-active state and clean EOF/exit. No prior root cause or latency distribution is proven. Reviewed one-job/40-minute affected Intel profile passed with the unchanged 30-second startup deadline; current functional scope is qualified, not general reliability. |
| E16-4 | Same actual CycloneDX 1.6 inventory, 6,496 components/6,497 dependency records: canonical/schema validation, independent target-marker/pinned-reader comparisons and five pre-API malformed-BOM refusals. Unknown native versions retain file hashes; no legal or native vulnerability clearance inferred. |
| E16-5 | All 80 unauthenticated public asset downloads match qualified names/sizes/SHA256; immutable attestation, enrolled metadata and all four archive descriptors verify. Public tree passes canonical SBOM admission. Fresh public macOS arm64 install/version/setup/source hashes and forced enrolled rc.16 public discovery pass. Separate actual public rc.15 refusal → explicit online rc.16 installer preserves failed cache/synthetic state, then discovers rc.16. Both private roots removed. No other-platform fresh public consumer execution is inferred. |
| E16-6 | Four prepublication signed native discovery journeys pass: real old-client refusal, explicit signed rc.15→16 upgrade and enrolled current-public rc.15 read, with root cleanup. Postpublication same-version rc.16 discovery is real availability/authentication evidence; it is not a newer-version notice/confirmed guided upgrade/restart. |
| E16-7 | Protected original preparation passed 3,960 source / 2,919 wheel tests, 86% source coverage and audit clean for 54 packages; controller/evidence PR #371 merged normally after 15 successful/3 deliberately skipped checks. Recovery controller PR #372 and concrete protected owner approval are linked in the publication record. Fresh pinned uv 0.13.4 no-dev audit again reports no known vulnerabilities/adverse statuses across 54 runtime packages. |
| E14-L | Historical signed rc.14 macOS arm64 both-store subscription chat/cold resume and coding through bound reviews, creator approval, integration/fresh tests: 28 dispatches/26 completions, two planned uncertain cancellations, twelve valid ModelReviews, eight workers absent. Original harness failure and separately authorized SQLite continuation remain unchanged. No fresh rc.16 inference or new grant. |

C15→C16 changes only `app_release.py` among 418 runtime Python files: the other
417, runtime export, Dockerfile and both subscription adapters are identical.
This supports reuse of unchanged contract logic, not fresh artifact/native-client
execution. C14→C15's setup diagnostics remain disclosed by the historical matrix.
Historical native clients were Codex 0.163.0 / Claude Code 2.1.283 with the explicit
120-second no-memory/tool-free profile; no present-day client/auth or OS equivalence
is invented. Missing boundaries still need fresh scoped authority and evidence.

## Production-template gates and owned findings

Critical offline/compatibility and exact preview distribution gates pass in E16's
scope. Whole-product privacy, OS/profile, manager, operations/restore, license and
owner-policy gates remain open. All open findings are owned by **Joshua Myers**,
checkpoint **2026-11-12 or before stable approval**, with no risk exception accepted
by this assessment. P1 blocks stable until direct evidence or legitimate scoped
owner disposition; P2 is process debt. Gaps are not claims of exploits or absent
implementation.

| ID / priority | Disposition and required acceptance |
|---|---|
| R14-01 / closed, retained | Useful SBOM defect was resolved in rc.15; independently verified again on public rc.16. Old empty rc.14 inventory remains immutable history. |
| R15-01 / closed defect for rc.16 | Bounded 2 MiB unsigned inventory, unchanged 128 KiB signed metadata, fixed ten-release selection and controlled JSON refusal are qualified. All four signed discovery and fresh public rc.16 native checks pass. Old immutable rc.15 binaries still need an explicit verified new installer; they do not repair themselves. Broader future update composition is R16-01. |
| R16-01 / P1, M09 residual lifecycle | Actual newer-public-version notice, user-confirmed guided upgrade/restart and required real same-owner session/grant/ledger preservation remain open. Current same-version lookup and synthetic sentinel/cache preservation do not establish them. Use a genuine future newer public release when available; retain controlled signed fixtures without fabricating public evidence or renewing grants. |
| R16-02 / P1, carries R15-02 | Review exact advertised stable profile/equivalence and missing M03–M08 native OS/auth/containment, actual Windows-hosted general WSL2, enabled-memory/allowed inspection/direct-review and two-real-principal privacy/egress cases. Preserve historical live evidence; do not silently narrow product scope or repeat paid permutations without a distinct boundary. |
| R16-03 / P1, carries R15-03 | Fresh public npm/tap versions and absence/presence of cask are bound below. Current public manager install/actual-predecessor upgrade/origin-conflict/restart/uninstall need reviewed releases. Apple Developer ID/notary custody, signed/notarized payloads and quarantined arm64/Intel Homebrew lifecycle precede cask availability; default-tap acceptance is separate. |
| R16-04 / P1, carries R15-04 | Owner-accepted whole-product SLIs/SLOs, denominator and representative p50/p95/overload/dependency failure, content-free event schema/independent health/loss, support/escalation and budget remain open. The non-reproduced Intel startup failure is retained operational evidence, not a fixed reliability incident or invented percentile. A cloud stack is not required. |
| R16-05 / P1, carries R15-05 | Accepted RPO/RTO and synthetic private-state/ledger restore plus owner-controlled signing-custody backup/restore/rotation remain open. Updater backups and epoch refusal are narrower. Never inspect keys or overwrite active ledgers for assessment. |
| R16-06 / P1 owner disposition, carries R15-06 | Fresh host observations below retain action/security/enforcement gaps. New secret-free owner-gated main-only recovery publication leaves signing custody unchanged; it does not close other server enforcement gaps. Owner chooses controls or dated justified exceptions; no new exceptions are accepted here. |
| R16-07 / P2, carries R15-07 | Resolve >=85% brief versus enforced 84% coverage policy (actual candidate 86%); review allowed merge methods, branch retention, disclosed zero-reviewer solo-owner policy and signing capability. Do not rewrite history or revoke passing checks without owner disposition. |
| R16-08 / P1, carries R15-08 | Record actual license suitability/obligations, treatment of unknown native versions and external-client/OS exclusions, owner acceptance and maintenance cadence. SBOM counts and clean Python audit alone do not close this. |

## Fresh observations and ordered next work

Fresh host settings: Actions policy `all`,
SHA pin enforcement `False`; native security
analysis `{"dependabot_security_updates": {"status": "disabled"}, "secret_scanning": {"status": "disabled"}, "secret_scanning_non_provider_patterns": {"status": "disabled"}, "secret_scanning_push_protection": {"status": "disabled"}, "secret_scanning_validity_checks": {"status": "disabled"}}`.
Main required checks strict/up-to-date `False`;
required approval count `0`;
commit signatures required `False`;
private reporting `False`;
branch auto-delete `False`.
Vulnerability-alert endpoint observation `{"http_status": "404", "observation": "unverified"}`
remains explicitly unverified when access/status cannot establish its setting.
Existing pinned workflows/gitleaks and no-bypass owner gates are compensating
evidence; they do not silently change or close these host-policy decisions.

Observed `2026-11-07T01:38:20.475002+00:00`: npm dist-tags
`{"latest": "0.0.0-stage", "preview": "0.1.0-rc.1"}`; formula versions
`["0.1.0-rc.2"]`; cask paths
`[]`. These are actual observed manager routes,
not current rc.16 manager publication. Host API settings are retained in private
ordinary engineering records. Previously published artifacts and dated rc.15/rc.14 assessments
remain unchanged; no security setting changed except the explicitly reviewed
secret-free protected publication environment.

1. Freeze the advertised stable profile and review M03–M08 reuse/missing boundaries.
   Prepare the provider-free two-actual-principal walking skeleton on snapshot and
   SQLite with synthetic sentinels, same-owner concurrency and foreign-owner refusal
   before any dependent external calls. Actual WSL2 and native-auth/containment
   coverage need their real target environments and fresh scoped authority.
2. Keep R16-01 as a genuine future-public-release lifecycle case; current corrected
   discovery is complete. Do not reopen the fixed cap or create a release merely
   to fabricate a newer-version test.
3. Advance manager/cask custody, license disposition and operations/restore work
   independently, with exact owners, evidence and explicit legitimate decisions.
4. Review all remaining gates before exact stable artifact/support approval.

Files/snapshot and SQLite remain the first backend scope. Native Windows 0.1.1,
post-Windows embedded terminals, PostgreSQL/S3 and deferred §31 automation are not
silently added. G3/G5/G6 studies/learned routing remain deferred under ADR-0011;
no comparative study, future schedule, staffing budget or stable approval is
created. The accepted result is **published rc.16 preview; stable v1 blocked**.
