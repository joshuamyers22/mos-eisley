# Full conversational v1 production-readiness record

- Status: **not ready for production launch**
- Owner: Joshua Myers
- Assessed: 2026-09-28 UTC
- Candidate: `feat/production-readiness`, based on `3e753c5` (the open #241 lineage)
- Scope: the full conversational v1 product requested by the owner on 2026-09-28,
  not the narrower private G2 library

## Objective and evidence rule

The intended journey is to install `mos` on a supported machine, start a live
conversation in a project, inspect and change code with authorized contained
tools, request independent review, save/resume safely, and update or recover the
installed product. Production readiness requires the exact release artifact and
all of those journeys to pass their applicable capability and operational gates.
An offline fixture, a source-tree command, or a qualified G2 campaign for an
earlier image does not establish that journey for a new release.

The authoritative product scope is the [plan's conversation contract](mos-eisley-plan.md#160-conversational-product-contract),
[v1 diff-panel requirement](mos-eisley-plan.md#1641-v1--live-full-screen-diff-panel),
[platform contract](mos-eisley-plan.md#27-windows-platform-release-contract),
[updates](mos-eisley-plan.md#28-application-update-notifications-and-guided-upgrades),
[installation](mos-eisley-plan.md#29-codex-style-installation-and-first-launch),
and [release checklist](../checklists/RELEASE_READINESS.md). The
[project brief](../PROJECT_BRIEF.md), [roadmap](ROADMAP.md), and
[G2 launch admission](REVIEW_LAUNCH_ADMISSION.md) distinguish implemented
boundaries from operating authority. Study timing remains governed by
[ADR-0011](adr/0011-defer-studies-until-production.md).

## Gate inventory

| Gate | Observed evidence | Remaining acceptance evidence | Status |
|---|---|---|---|
| Reviewed integrated release baseline | GitHub main is `0ce5c54`; #241 (G3/G4/plan) and #240 (G2 owner live review) are open; #241 checks passed at `3e753c5` | Review and integrate the required feature lineage, then requalify the exact release candidate | Open |
| Live conversational journey | `mos` starts the recorded TUI and `chat`/`resume` exist; the brief explicitly says live conversation remains open | Live provider conformance, transfer and aggregate spending gates, installed-artifact end-to-end chat, steering, cancellation and resume | Open |
| Repository work and review | G4 has offline containment, Git and reviewer gates; G2 has a three-slot private read-only qualification | Real authorized coding-child and reviewed correction chain, contained repository tool operation, actual critic/judge quorum and independent review on the candidate; public review integration with an exact launch decision | Open |
| V1 interface | Recorded TUI and scoped memory exist; roadmap lists live diff panel as required v1 work | Live diff, frozen line attachment, stale-view and resize/workspace-switch tests; long-session storage and owner-isolation gates | Open |
| Provider and platform coverage | Current G2 private qualified profile is OpenAI Luna/low; 0.1.0 plan names macOS/Linux and WSL2 | Qualify advertised creator/critic/judge roles and provider profiles; installed-wheel and contained runtime gates on every advertised OS, including WSL2 | Open |
| Installation and updates | README documents a local wheel build and `uv tool install`; release workflow builds wheel/sdist and SBOM | Verified standalone, npm, Homebrew and direct-download journeys; first-launch setup; feed, notice, guided update, state-preserving recovery, clean-machine tests per plan §§28–29 | Open |
| Release provenance | This branch adds exact tag/checkout/main ancestry checks before project install, makes publication wait for secret scanning, and records source-commit/checksum files | CI on the merged candidate; protect release tags and require accountable release approval; validate published artifacts and rollback from the exact built release | Partial |
| Operations and support | `SECURITY.md` identifies the owner but explicitly has no production support SLA | Published response commitment, incident owner, logs/metrics/alerts, capacity/latency and recovery evidence, plus reviewed rollback procedure | Open |
| Studies | ADR-0011 defers all studies | Production launch and actual owner-authorized operation precede any separate prospective study approval | Disabled |

The GitHub branch-protection API reported required `quality`, `container`, and
`gitleaks` checks, conversation resolution, and **zero required approving reviews**
on `main` at assessment time. The repository ruleset query returned no rulesets;
the legacy tag-protection endpoint returned 404, so tag protection remains
unverified. No deployment environment was returned. These external settings must
be checked again at release time. A workflow file on an unreviewed tag can itself
change; repository policy must restrict who can create release tags. The new
mainline ancestry check reduces accidental publication from an unmerged branch,
but is not a substitute for that repository policy.

## Current bounded verification loop

Selected guidance: [AGENTIC_VERIFICATION_GUIDE](AGENTIC_VERIFICATION_GUIDE.md),
[verification-loop template](../templates/AGENTIC_VERIFICATION_LOOP.md),
[work-note template](../templates/WORK_NOTE.md), and
[threat-model template](../templates/THREAT_MODEL.md). The release workflow is a
high-risk publication boundary requiring accountable human review.

- Invariants: no study execution before launch; no public live dispatch without
  current exact authorization; no release from an unmerged commit; no credential
  material in source or artifacts; failed/uncertain provider effects retain
  conservative spending and no automatic retry.
- Non-goals for this slice: claiming v1 launch, making a provider call, enrolling
  cases, changing GitHub protection, tagging, publishing or deploying.
- Resource ceiling: two evidence-changing local verification passes; no provider
  spend. Stop on focused test failure, the combined repository gate, or a missing
  accountable approval/operating input.
- Rubric: exact mainline tag check is blocking; release artifact traceability is
  blocking; no regression in source/package checks is blocking; remaining v1
  journeys are blocking for the overall production decision.

| Pass | New evidence | Finding and disposition |
|---|---|---|
| 1 | GitHub PR/protection queries, roadmap/brief and CLI inspection | Full v1 is not operational; release workflow accepted a metadata-matching tag without mainline proof. Add a fail-closed check. |
| 2 | Synthetic local Git repos with a tagged main commit, an unmerged tagged side commit, and a mismatched checkout; locked runtime audit; combined gate | Main case passes; side and mismatched checkouts reject. `make audit` found no known vulnerabilities in 45 audited packages. The first `make check` ran 2,543 tests but had 31 MCP fixture errors because the sandbox denied loopback socket binds. The permitted `make check` then passed: 2,543 source tests, 88% coverage and 1,894 installed-wheel tests. Accountable publication review remains pending. |

## Sequence to reach a launch decision

1. Land and review the required feature branches on `main`; establish a single
   release-candidate commit and frozen capability list. Keep studies disabled.
2. Complete live conversation admission and the real G4 coding/review path,
   including exact provider, transfer, spend, containment and correction evidence.
3. Complete the v1 diff and installed distribution/update journeys, then run
   production-like end-to-end, failure, recovery and rollback checks on supported
   platforms.
4. Establish support and operational ownership, protect release tags, require an
   accountable release review, and rerun the release checklist against the exact
   commit, image and artifacts. Record the owner's launch decision separately.

No date is inferred for the remaining engineering work. Joshua Myers owns the
scope and approval decisions; implementation owners and target dates must be
assigned before the final release review. Current status stays **not ready**
until every blocking row has direct evidence.
