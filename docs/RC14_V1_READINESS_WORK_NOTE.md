# Work note: fresh v1 readiness assessment of published rc.14

- Status: closed; assessment delivered, full stable v1 remains blocked.
- Owner: Joshua Myers; operator Codex.
- Started/updated: 2026-11-04 UTC. Review by: 2026-11-11 or earlier scope change.
- Baseline: published `ec3211e23c4a3e2b20837114e707bc8ebcbe625a`, immutable
  `v0.1.0-rc.14`, release 434439039. Documentation starts from publication-closeout
  head `091f2b9642d3007311d599844bdab82f709936b5`; PR #361 has normal auto-merge
  enabled and is observed separately from release qualification.

## Objective and completion evidence

Assess full conversational v1 / stable 0.1.0 against the exact published artifact,
Mos Eisley's approved plan and production-template gates. Credit completed signed
and both-store live qualification without replacing historical failed controllers.
Deliver a requirement/evidence/status matrix, scoped limitations, owned residual
risks, concrete acceptance checks and an ordered next-work list. Correct current
entry-point documentation contradicted by the admitted evidence.

Guidance: repository `AGENTS.md`; adopted production standard and verification/
adversarial guides at template pin `8879be48f3b760e65f6bed32f8740314fe92910d`;
work-note, verification-loop and threat-model templates; release checklist.
Apply the fresh upstream-main checklist and integration/E2E guide/template at
`351610f91e91710a63316b631ff0d61a6c997458` (verified through GitHub), with the
adopted guides retained. The unrelated local template branch and dirty working
files are untouched. No wholesale guidance or repository-policy migration is
implied; current-template governance differences need explicit disposition.

## Rubric, bounds and threat model

Risk: material readiness/governance assessment; an operator assessment cannot
supply independent review or authorize a stable launch.

- Blocking rubric: every applicable product/template gate has direct evidence or
  an explicit gap; platform/provider/install-route scopes stay distinct; no old
  uncertainty or unsupported launch claim is erased; next actions have owners and
  decidable acceptance criteria.
- Two evidence-changing passes: (1) requirement/source/test and retained receipt
  trace; (2) fresh read-only public release, package/CI/governance observations and
  contradiction review. One correction/document-validation pass; three-hour ceiling.
- Zero inference, study, new grants, raw credential/key reads, publication mutations or
  full qualification reruns. No sampling registry, custodian mapping, label or
  outcome store is read. Ordinary engineering evidence grants no study eligibility.
- Preserve exact candidate/tag/assets, all closed campaign roots, unpublished
  fixtures and unrelated template edits. Do not run provider/telemetry tasks.
- Threats: scope inflation from narrow tests, stale status, unverified recovery,
  unsigned artifact substitution, diagnostic content leakage and independent-review
  overclaim. Controls: exact-source/hash links, explicit scope/status labels,
  native trust evidence, sanitized findings and retained uncertainty.
- Stop after a complete matrix and checked documentation; report missing evidence
  instead of fabricating it. Owner-dependent gates remain open. A proposed
  risk-review date is not an accepted operational delivery commitment.

## Verification and handoff

The [completed assessment](V1_PRODUCTION_READINESS_RC14.md) contains the installed
acceptance and template gate matrices, nine owned findings, evidence index,
reproducible SBOM defect and ordered integration/E2E handoff. It credits signed
four-target and both-store macOS arm64 live qualification without generalizing to
unobserved targets or reopening old uncertainty.

| Pass | New evidence | Result and disposition |
|---|---|---|
| 1 | Product §§16–17/27–29, release/public/live receipts, source/test trace, current native Apple signature metadata | Core release evidence is accepted for its actual scopes. Full v1 still includes WSL2, manager/cask, privacy and operations gates. |
| 2 | Fresh upstream-main template at `351610f`, public rc.14/tag/assets/run/governance and npm/tap observations, public SBOM download, current runtime vulnerability audit | Reproduced zero top-level SBOM components in 402 bytes; all 71 public asset identities still match. Audit passes for 54 packages. Record current-template governance differences and distinguish unavailable/unknown controls from disabled ones. |
| Correction/validation | Cross-document contradiction review, evidence-hash checks, relative links/anchors, frozen source/lock manifest and documentation-only scope | README/latency guidance now credit completed rc.14 live qualification; historical records retain prior failures. All 866 frozen non-Markdown inputs and candidate worktree remain unchanged. |

The first private documentation-checker invocation used the host's older
`python3`, which lacks `tomllib`; it stopped before checking documents. The same
checker passed with the project's declared Python 3.12 interpreter. This is a
harness invocation error, not a failed product gate, and is retained here rather
than labeled a first-attempt pass.

Checks: current `uv audit --preview-features audit-command --locked --no-dev`
exits 0 with no known vulnerabilities/adverse statuses in 54 packages; private
assessment validator passes evidence hashes, relative links/anchors, JSON SBOM
reproducer, coverage-policy discrepancy, doc-only scope and all 866 frozen input
hashes. `git diff --check` passes. The exact frozen candidate's combined
source/wheel gate already passed and is reused with its original attribution;
no new full runtime gate is claimed for this documentation assessment. Normal
required PR CI remains a merge gate.

Stop rule reached: every applicable gate has scoped evidence or an explicit gap;
next work is owned and decidable. First concrete engineering slice: R14-01,
useful SBOM generation plus fail-closed coverage validation in a new candidate.
No inference, signing-key inspection, study or release mutation was performed.
No human independent-review or stable-launch approval is claimed. Joshua owns
risk/scope/operating-budget decisions; accepted delivery dates remain unset, with
a proposed 2026-11-11 decision checkpoint.

Durable fact promoted as `delivery.v1-readiness.rc14` in `PROJECT_MEMORY.md`.
Assessment/observations remain separate from template policy adoption; no ADR or
repository-host control was changed. Private metadata and disposable checkers
stay ignored in `.work/`, with no provider payloads copied into tracked notes.
