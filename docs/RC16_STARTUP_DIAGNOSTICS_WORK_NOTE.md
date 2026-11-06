# rc.16 Intel staged-startup diagnosis

Owner: Joshua Myers; operator: Codex. Started 2026-11-06 15:46Z.
Objective: diagnose RC16-Q02 with bounded redacted timing/process-state evidence,
then fix the cause or justify an explicit qualification profile, repeat affected
Intel checks and all four signed discovery checks, and review before publication.
The owner's current request authorizes these steps. No publication, signing,
provider calls, private key/authentication or historical evaluation-store access.

Selected guidance: AGENTS, Python engineering, agentic verification/adversarial
playbook, verification-loop/work-note and threat-model templates, as pinned by the
production-template survey. Frozen runtime/tag remain 14eb79d / v0.1.0-rc.16.
New controller source is separately identified; original runs 42102119299 and
42233939365 and their failures remain unchanged.

Rubric (all blocking): exact enrolled artifact/source/bootstrap identity; bounded
content-free diagnostics and cleanup; no conversion of a >30-second startup to
an installer success; complete affected Intel assertions and four actual public
discovery receipts; full 62-report/80-asset reconstruction and independent SBOM
admission before any publication decision. Existing source/wheel gates and new
focused negative tests remain required. No inferred CPU/loader root cause.

Budget: six-hour window ending 2026-11-06 21:46Z; one diagnostic dispatch and one
affected qualification dispatch after evidence review, at most one evidenced
controller correction. Diagnostic job <=25 minutes, at most four staged version
observations of 120 seconds, <=8 KiB combined output per observation, <=16 fixed
numeric/process-state samples per observation. Preserve the original 30-second
failure threshold even when observing the same process longer; never rerun that
version call to obtain a pass. Qualification/native jobs remain bounded and have
no automatic retry. Stop on identity mismatch, unsafe output/process cleanup,
unexplained repeated failure, or exhausted budget; review before changing profile.

Threat boundary: only known staged `mos --version` in disposable runner roots is
observed. Persist fixed state enums, elapsed/CPU/RSS/load numbers, exit/output byte
counts and version-match flags; exclude command lines, process IDs, paths, env,
stack dumps and raw output. Use private process groups, bounded reads, fixed OS
queries and termination/reaping on deadlines. No unrestricted process inspection
or credential/network use by diagnostic native children. Changed observation
behavior is a diagnostic controller, not a qualified installer timeout override.

## Results and profile review

Eight offline process tests, explicit Ruff/pyright and workflow guard compilation
pass. All four affected Intel commands exactly match the preserved original
controller. PR #371's initial exact head `e2faad64005e125043c16759d5b50d9d0378edb7`
passed all executed CI checks; diagnostic/qualification/discovery were deliberately
skipped in the PR event, not called passing native checks.

One diagnostic dispatch, run 42246992124, produced two valid observations: staged
synthetic predecessor 9.699 seconds and candidate 12.848 seconds, exit 0, both EOFs,
no stderr or overflow, cleanup complete. At five seconds each process was running
with about 99–100% CPU and five seconds of CPU time. No 30-second overrun or stalled
process reproduced. This does not prove the old failure's cause or a distribution.

Operator review authenticated the exact signed bytes and content-free receipt,
then admitted one qualification dispatch: one affected Intel job, aggregate
40 minutes, unchanged installer deadline 30 seconds, no automatic retry, existing
48 exact predecessor journeys reused. This revises campaign composition and bounds,
not the native success condition; the original intermittent failure remains a
retained limitation. No product fix or signing retry was inferred from a
non-reproduction. The approval/tool wait delayed actual qualification creation to
19:45:54Z; no additional native run was launched during that wait.

Run 42282492215 passed signed Intel installation/recovery, both-store installed
acceptance, six-case offline diagnostics and generated Homebrew formula checks,
then all four actual signed public-discovery journeys. Reconstruction passes 62
base reports/80 assets and 48 actual predecessor journeys, with four supplementary
discovery receipts kept separate. Full independent SBOM/schema/marker/reader and
five pre-API rejection controls pass; read-only publisher preflight passes. All
18 software hashes remain unchanged. Complete evidence is reviewed in
[the final qualification record](RC16_STARTUP_QUALIFICATION_REVIEW.md).

The first full reconstruction refused the fresh smoke report's checkout identity;
source inspection established that its `source_commit` is `git rev-parse HEAD`.
The corrected auditor requires exact reviewed controller identity for that one
field, byte-identical original smoke code and enrolled archive/bootstrap bindings;
all runtime source checks remain 14eb79d. No receipt was edited. Original refusal
is retained separately.

The combined local `make check` source phase passed, but wheel dependency setup
failed after PyPI connection timeouts; its exit 2/log/input snapshot remain retained.
A network-enabled retry repeats only `make smoke`, not already successful source
checks. Exact-head GitHub source/package gates independently passed. Main's merged
#370 record was reconciled with the diagnostic branch; all 883 original non-Markdown
controller inputs remained identical. New tracked JSON files are bounded ordinary
release evidence, not runtime/controller inputs or evaluation artifacts.

Current task launches: one diagnostic and one affected qualification, zero provider
calls, signing operations or publication. Historical failures, sources, grants,
ledgers and dated rc.15 assessments remain unchanged. Native work and independent
qualification review finished inside the declared six-hour window. Normal PR CI
and owner-directed technical review remain required before merging the evidence.
The original publisher is skipped; no alternate publisher or owner publication
approval is created by this work.
