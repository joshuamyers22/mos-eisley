# rc.9 frozen Linux launcher repair and qualification

- Status: technical qualification complete; owner publication disposition pending
- Owner: Joshua Myers; implementation and technical verification by Codex
- Started: 2026-10-25 UTC
- Base: immutable rc.8 source `eadb415d31afd89b142e3229a8ccca72aca835ee`
- New candidate: `0.1.0-rc.9`, retaining rc.8 dependencies and storage epoch 2
- Review point: exact native qualification before any publication

## Objective and invariants

Repair [RC8-Q01](https://github.com/joshuamyers22/mos-eisley/blob/017f00743d15435e02e030ecfab9992314a65b1b/docs/RC8_PREPUBLICATION_REVIEW.md#blocking-finding):
frozen Linux must invoke its fixed confined Git helper, not treat
the native executable as a Python interpreter. Preserve the source/wheel isolated
module route, seccomp ABI validation, process/network denial, absolute executable
checks, bounded process ownership/deadlines and fail-closed behavior. No generic
Python/module executor, external-interpreter fallback, new provider authority or
isolation bypass. Preserve rc.8 tag/artifacts and its failed qualification.

The user requested a new candidate and repeated affected qualification. This
includes preparation/signing and native acceptance, not publication, inference
or studies. Preserve the owner's selected rc.8 dependency set; main's separate
SDK/HTTP migration does not enter this candidate.

## Guidance and verification contract

Retrieved AGENTS/CONTRIBUTING, README/brief/memory, RC8-Q01 review, launcher and
process tests, packaging/release workflows and installed acceptance tooling.
Selected Python engineering, bounded verification guide/loop, threat-model,
adversarial review/playbook, work-note template and release checklist.

Security-sensitive packaging change. One focused contract/OS-boundary pass, one
combined full `make check audit`, exact protected PR checks, then clean frozen
native and signed qualification. Four hours per full/native gate; at most two
evidence-backed corrections per new failure; zero provider spend. Stop dependent
work on failed assertions, identity/state/signature mismatch or exhausted bounds.
No test skips count as platform qualification. Agent technical review is not
independent security or accountable release approval.

| Blocking requirement | Acceptance evidence |
|---|---|
| Fixed frozen dispatch | Exact private Linux-only mode reaches only `_git_read_linux`; ordinary CLI behavior and non-frozen mode retain contracts |
| Confinement before execution | Invalid paths/platforms refuse; seccomp failure prevents exec; real frozen Linux Git succeeds while process/network probes fail |
| Artifact qualification | Actual native terminal/diff, stale attachments, both stores, cold resume/recovery and actual predecessor epoch refusal on exact new archives |
| Supply chain and identity | Frozen lock changes only project version; source/wheel/static/audit/container checks and exact-tag/main ancestry, signed metadata/archive identity |
| Publication boundary | Separate publication approval withheld pending final evidence review |

## Threat and authority trace

The private mode is recognized only in the frozen Linux entry point, before the
CLI/provider composition root is imported. It selects one compiled-in module;
arguments cannot name Python code or another module. Existing helper validates
the absolute executable and installs the same seccomp filter before `execv`.
Git command/path authorization remains in the trusted read broker. Direct host
invocation supplies no model/tool authority, network grant or release permission.

The native regression uses a host diagnostic interpreter only as the executable
whose fork/socket syscalls must be denied. Actual Git operation and product
startup remain self-contained; no external interpreter substitutes for the
frozen launcher. No credentials enter those probes.

## Verification and attempts

- Initial `uv sync` failed because the sandbox could not resolve the package
  index. Retry uses the exact frozen lock with native network permission; no
  dependency versions were changed. `uv lock --offline` changed only rc.8 to rc.9.
- Five new frozen-dispatch tests pass, including wrong host/mode, fixed arguments,
  invalid targets, confinement failure and execution ordering. The first test
  draft expected a string where `execv` receives a valid Path and had untyped
  mock lambdas; corrected test types/expectation, with no product guard change.
- Distribution regression: 42 tests pass. Publication/workflow regression: 15
  tests pass, now requiring the nonoptional installed-candidate gate. Three
  candidate source/version/epoch/result negative guards pass. Ruff/format and
  strict typing pass after import-order normalization.
- The rc.8 installed driver is generalized to explicit expected source/version
  arguments and the new fixed launcher, then made a required signed job step.
  Native development and signed smoke now require real Git success plus actual
  process/network denial; non-Linux native entry must refuse the private mode.
- Focused Git/OS boundary regression: 24 tests passed with native process
  permission. The first result was lost to output truncation; the captured
  verification ran 24 cases in 20.536s with no failures.
- Combined awake `make -j1 check audit` passed: 3,880 source tests in 2,874.376s
  (17 platform skips), 86% coverage, 2,856 clean installed-wheel tests in
  2,025.371s (13 skips), export verification and package builds, and no known
  vulnerabilities/adverse statuses in 54 audited packages. All eight recorded
  implementation/release input hashes stayed unchanged during this gate.
- Post-gate inspection found that an installed-matrix failure would skip the
  signed report upload. Made that upload unconditional while keeping the failed
  job blocking publication; required that contract in the existing workflow test.
  Only that workflow assertion/upload and candidate documentation changed after
  the full gate. All 15 publication/workflow tests, whole-tree lint/format,
  strict typing and whitespace checks passed on the follow-up.
- Main's newer formatter/linter accepts all seven checked changed Python files.
  Separate integration environment preparation hit sandbox DNS refusal; exact
  frozen retry with network permission succeeded, preserving main's SDK/HTTP
  migration. No dependency versions changed in the frozen candidate.
- Exact protected release `40246538826` passed all four native builds and all
  four signed jobs. Preparation passed 3,880 source tests (17 skips), 2,856
  installed-wheel tests (13 skips), 86% coverage, clean 54-package audit,
  container checks and SBOM. Its source/wheel runtimes were 4,018.651/2,652.862s.
- Review verified enrolled metadata signature, source/version/epoch, all root,
  archive and bootstrap hashes, all 30 native receipts and the 47-asset inventory.
  Every target passes the installed matrix on both stores. All 20 actual upgrade
  pairs prove epoch refusal/preservation, including rc.7 on all four targets.
  No provider calls or studies ran. See [the final review](RC9_PREPUBLICATION_REVIEW.md).
- Preparation ran 116m45s and the slowest signed job 37m45s, within declared
  bounds. Read-only status watchers hit connection/TLS errors; reconnects did
  not rerun remote tests. Fresh final records and artifacts confirm results.
  Approval history has preparation only; the separate `publish` job is waiting.

## Main integration

Frozen candidate source is `f94842a44b9fc5dcf42a7f5880a6683e4fdc0b23`.
It was integrated into main base `5e67b4c523d57f8e85ff08b8f1c1fd51ee7dfb88`
with both parents preserved. The memory-index conflict was resolved by retaining
both delivery keys and correcting rc.8's disposition to blocked RC8-Q01.
Main's requirements, SDK privacy guard, SDK tests and newer action pins are
unchanged; its manifest/lock change only the project version. All eight checked
launcher/harness implementation and test files match the frozen candidate.

The combined integration passes 35 focused cases (5 frozen entry, 12 provider,
15 workflow/publication and 3 identity guards), whole-tree lint/format/typing,
explicit qualification-tool typing, whitespace and runtime-export verification.
Refreshing the integration's local project version hit sandbox build-index DNS;
the follow-on commands were interrupted and exact frozen checks reran with
network permission. No failed test or guard was suppressed. All 13 protected
checks subsequently passed. PR #336 merged at `a73edc655c78be15e54aa8a7649cb7479a1f8566`;
the annotated rc.9 tag pins the frozen candidate. The tagged release repeated
its own exact-source full and signed gates successfully.

## Handoff

Keep disposable logs and artifacts in ignored `.work/`. Retain exact code and
artifact identities, counts/skips, errors and dispositions without raw prompts,
credentials, private keys, sampling registries, custodian mappings, labels or
study outcomes. Record final technical review and remaining owner decisions here.

## Verification-loop exit

| Pass | Added evidence | Disposition |
|---|---|---|
| Focused + full local | Fixed-entry security contracts, actual Git boundary, clean wheel, static checks and audit | Pass; test-draft typing/Path expectations corrected without weakening guards |
| Protected integration + tagged builds | Current-main full CI, four native architectures, real process/network denial | All 13 PR checks and four tagged native builds pass; main SDK migration preserved |
| Exact signed acceptance | Enrolled native installs, two stores, real terminal/diff, actual old archives and epoch refusal | All 30 receipts pass; RC8-Q01 closed only for new rc.9 |
| Evidence review | Signature, exact identities, retained predecessor digests and complete 47-asset inventory | Pass; RC9 report-retention gap covered by unconditional upload and workflow contract |

Stop reason: requested technical qualification achieved. No unresolved failure
remains in that scope. Accountable owner review/publication, broader v1 and
operational/provider gates remain separate; this task grants no publication or
inference authority. The original rc.8 failed evidence remains preserved.
