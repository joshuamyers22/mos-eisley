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
