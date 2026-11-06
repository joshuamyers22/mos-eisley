# rc.16 staged-startup diagnosis and final affected qualification

Disposition: **affected signed qualification passes under the reviewed bounded
profile**, for frozen `14eb79d52950f340aba159815222e04e6ea864e3`, version
`0.1.0-rc.16`, epoch 2. Runtime, tag and signed software remain unchanged.
Publication is not authorized or performed. The original Intel failures remain
unsuccessful; their root cause is not proven or described as fixed.

## Diagnostic evidence and profile decision

The owner explicitly authorized bounded redacted diagnosis, an evidenced fix or
profile decision, affected Intel checks, four-target discovery and evidence review
before publication. This is owner-directed operator review by Codex, not an
independent human attestation or stable-v1 approval. Selected production-template
and threat guidance, acceptance criteria, six-hour budget and stopping rules are
in the [work note](RC16_STARTUP_DIAGNOSTICS_WORK_NOTE.md).

[Diagnostic run 42246992124](https://github.com/joshuamyers22/mos-eisley/actions/runs/42246992124),
controller `e2faad64005e125043c16759d5b50d9d0378edb7`, authenticated the exact
signed archive/bootstrap/metadata and replayed the original smoke fixture only
through the formerly failing staged-version call, before activation. It observed
each process once, with a 30-second failure threshold and a maximum 120-second
observation. Raw output was discarded. The receipt contains fixed process states,
numeric timing/CPU/RSS/load, byte counts and EOF/exit/version flags, without process
IDs, paths, command lines, environment values or stack dumps.

The synthetic predecessor completed in **9.699 seconds**, and candidate rc.16 in
**12.848 seconds**. Both returned the exact version, exit 0 and both output EOFs,
with no stderr or output overflow. Five-second observations showed running state
and about 99–100% CPU, with roughly five seconds of process CPU time. This proves
CPU-active startup in those observations; it does not identify the prior timeout's
loader, scheduler, scanner or code cause. No stalled process or late result was
reproduced. Sampling overhead and two contextual observations do not establish a
latency distribution or general Intel reliability.

Review admitted **one qualification dispatch** with one Intel job for the four
affected assertions, a 40-minute aggregate job budget, and the **unchanged
30-second native startup deadline**. Previously authenticated twelve-predecessor
results were reused, preserving their source/artifact identities and failures.
Four public-discovery jobs were conditional on the Intel job succeeding. This
separates the aggregate historical matrix from the affected acceptance work;
it grants no automatic retry or relaxed installer success condition. No product
change or re-signing was justified by the non-reproduced incident. Eight actual
process tests cover late result, silent deadline, inherited pipe, output cap,
invalid result/exit, redaction and invalid bounds. Late valid output never converts
a failed original deadline into a pass.

## Fresh installed qualification and reconstruction

[Qualification run 42282492215](https://github.com/joshuamyers22/mos-eisley/actions/runs/42282492215)
used the same reviewed controller, required the exact successful diagnostic
artifact, and passed all four original Intel assertions unchanged: enrolled signed
installation/recovery, snapshot and SQLite terminal/diff/cold-resume acceptance,
six-case offline native diagnostics, and actual generated Homebrew formula
install/launch/test/uninstall. Its diagnostic job was deliberately skipped and is
not counted as another probe or a passing qualification case.

Reconstruction authenticates **62 base reports and 80 publication assets**:
46 reports from the three original full platform jobs, twelve Intel predecessor
reports from the retained continuation, and four fresh Intel reports. Old partial
and duplicate Intel reports remain in their original roots. The completed matrix
covers all four macOS/Linux arm64/x86_64 targets, **48 actual predecessor journeys**,
actual rc.15 upgrades, rc.7 cross-epoch downgrade refusal, four both-store matrices,
four offline diagnostic matrices and two Homebrew formula journeys. All report,
metadata, archive, bootstrap, formula and harness bindings are checked.

An initial reconstruction correctly refused the fresh Intel smoke report because
the old auditor assumed its `source_commit` meant packaged source. The unchanged
smoke tool actually records `git rev-parse HEAD`, the controller identity. Review
requires exactly `e2faad6` for that field only, verifies the smoke tool is byte-for-byte
the original frozen tool, and independently binds its archive/bootstrap to enrolled
runtime `14eb79d`. All other runtime-source checks retain the frozen source.
No report bytes or artifact identities were rewritten; the first refusal is retained.

## Four actual signed public-discovery journeys

All four native targets passed using actual unchanged signed rc.15 and rc.16
installers in disposable private roots with no host Python/Node on their native
PATH. Each reproduced old rc.15's refusal against the real **914,579-byte** public
feed, explicitly installed rc.16, preserved synthetic state and the old failed
cache through that upgrade, then performed fresh native public discovery.

Each rc.16 client authenticated enrolled current public rc.15 metadata and
reported itself installed at rc.16, up to date, with no available update or notice.
Discovery preserved the runtime pointer and synthetic state, and all private roots
were removed. These are actual public-read checks, with zero provider calls;
they do not requalify real grants, uncertainty ledgers or live coding. Public rc.15
remains immutable and current. A genuine newer-public-version notice/confirmed
upgrade/restart still requires a future newer public release. Old clients need the
explicit verified new installer after rc.16 publication to receive this fix.

## Full SBOM and publication admission review

The same CycloneDX software inventory, **6,496 components/6,497 dependency records**,
passes complete canonical recomputation and official offline 1.6 schema checks.
Independent standard marker evaluation agrees on 44 Linux/42 macOS packages;
pinned PyInstaller reader hashes/sizes agree on all bootstrap members. Five actual
mutated-BOM controls are rejected before API access. Complete 80-asset inventory
and read-only publisher preflight pass; all 18 original prepared software file
hashes are unchanged. All 418 packaged runtime Python sources had already matched
in every archive, and those archive bytes remain identical.

Unknown native versions remain hashed file identities. No new vulnerability,
license, platform, latency-distribution, live subscription or stable-v1 approval is
inferred. rc.14 live receipts remain historical. The dated rc.15 readiness and
acceptance records are unchanged.

## Evidence and remaining publication boundary

[Ordinary release receipts](qualification/rc16/) retain the redacted diagnostic,
operator review, complete base reconstruction, independent SBOM review, four
individual discovery receipts, discovery reconstruction and software-preservation
review. These convey no evaluation eligibility; no sampling registry, outcome,
label, prompt, model response or provider output is included.

The original protected run 42102119299 remains cancelled, and its publisher remains
skipped. Read-only continuation does not make it green. Actual publication needs a
separately reviewed protected path that admits this exact complete evidence,
followed by explicit owner publication authorization. No draft, asset overwrite,
tag retarget, signing retry or provider call occurred during this task.
