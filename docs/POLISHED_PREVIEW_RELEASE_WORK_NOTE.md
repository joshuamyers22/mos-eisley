# Polished interface preview preparation

- Status: active
- Owner: Joshua Myers
- Started: 2026-10-15 UTC
- Baseline: main `3d7f089`, including interface merge `b79d970` (PR #306)
- Candidate version: `0.1.0-rc.3`
- Published predecessors: immutable rc.1 at `8cf38c8` (release 413060239),
  immutable rc.2 at `ef6a66f` (release 413979297)

## Objective and authority

Prepare an installable macOS/Linux preview containing the accepted interface,
confirm post-merge quality, qualify installation and real published-predecessor
upgrades, and present the exact publication candidate for accountable review.
The published rc.2 predates the interface merge and cannot be replaced.

Use a new isolated worktree. Preserve user installations, credentials, sessions,
configuration, spending evidence and all existing worktrees. Qualification uses
disposable roots and recorded fixtures; no provider calls or study execution.
Keep the enrolled signing root, immutable tag/version rules, protected owner
environment and draft-first publication. Publication approval remains attributable
to Joshua; technical agent review does not supply independent security approval.

Selected guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
`templates/WORK_NOTE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md` and `checklists/RELEASE_READINESS.md`.

## Rubric and stopping rules

| Dimension | Blocking evidence |
|---|---|
| Source | Post-merge CI and candidate full quality gates pass; exact mainline source/version identities retained |
| Installation | Enrolled-key signed artifacts and real native bootstraps on macOS/Linux ARM/x86; Python/Node absent from PATH |
| Upgrade | Both rc.1 and rc.2 to rc.3: JSON/SQLite cold resume, candidate-written-state rollback, interrupted activation recovery, tamper refusal and uninstall |
| Publication | Complete exact artifact inventory and SBOM, immutable source/tag/version, owner disposition and protected signing/publication gates |

Risk: material release/supply-chain qualification. Bound: one coherent full gate
per candidate snapshot, three evidence-changing correction passes, configured
native/CI timeouts, and zero provider spend. Stop on identity/signature mismatch,
lost or retargeted state, failed rollback/recovery, incomplete inventory or missing
accountable release disposition. A changed candidate needs fresh exact-artifact
qualification. Stable v1, Homebrew cask, WSL2 and general subscription reliability
remain separate milestones.

## Trust review

Published predecessor selection stays allowlisted to exact immutable release
versions and source commits. The helper verifies enrolled signatures, exact source,
archive size/hash and published bootstrap checksum before execution. Unknown
versions, substituted source/metadata and altered archives fail closed. Both
predecessor journeys must finish successfully before tagged publication; their
evidence filenames are distinct. Key bytes and real user data stay out of Git,
logs and public artifacts. Owner signing custody and release accountability remain
required controls.

## Evidence and handoff

- rc.2 is immutable and points to `ef6a66f`; its published assets do not contain
  interface merge `b79d970`. It is retained untouched.
- Post-merge distribution and secret scanning passed on `b79d970`; source/package
  CI was still running at task entry. Record the completed result before release.
- Current-main OpenTelemetry update `3d7f089` is included in the new candidate;
  earlier candidate qualification does not certify these new runtime bytes.
- Next: rc.3 metadata, mandatory rc.2 upgrade admission alongside rc.1, focused
  refusal checks, full/native qualification, exact artifact review and owner
  publication disposition.
