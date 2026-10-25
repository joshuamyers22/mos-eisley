# rc.9 frozen Linux launcher repair and qualification

- Status: active
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
  signed report upload. Make that upload unconditional while keeping the failed
  job blocking publication; require that contract in the existing workflow test.
  Only that workflow assertion/upload and candidate documentation changed after
  the full gate. All 15 publication/workflow tests, whole-tree lint/format,
  strict typing and whitespace checks passed on the follow-up.
- Main's newer formatter/linter accepts all seven checked changed Python files.
  Separate integration environment preparation hit sandbox DNS refusal; exact
  frozen retry with network permission succeeded, preserving main's SDK/HTTP
  migration. No dependency versions changed in the frozen candidate.
- Native/signed qualification and final disposition: pending.

## Handoff

Keep disposable logs and artifacts in ignored `.work/`. Retain exact code and
artifact identities, counts/skips, errors and dispositions without raw prompts,
credentials, private keys, sampling registries, custodian mappings, labels or
study outcomes. Record final technical review and remaining owner decisions here.
