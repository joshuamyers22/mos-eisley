# Agentic Verification Loop: G3 context-study seal and label inventory

## Objective and authority

- Requirement: roadmap G3; plan §§6.7.6, 18.1–18.3 and 26.3–26.5
- Outcome: freeze baseline/full-candidate/component-ablation arms and inventory only
  independently signed label metadata before any held-out session inspection
- Invariants: no session/dataset payload, two distinct trusted graders, disagreements
  and unknown probabilities ineligible, complete outcome/ablation families, no execution
  or promotion authority
- Risk class: material data integrity and study governance
- Implementation owner: Codex under Josh Myers's direction
- Accountable approval: Josh Myers and an independent statistical/data reviewer
- Starting revision: `bac7dd2`; existing uncommitted G3 feasibility work retained

## Rubric and stopping rules

| Dimension | Severity | Evidence | Pass threshold |
|---|---|---|---|
| Held-out non-inspection | Blocking | Strict contracts and CLI surface | No brief, dataset, session or outcome input; literal false inspection flags |
| Independent eligibility | Blocking | Signature and negative tests | Two distinct enrolled keys agree; tamper/disagreement/unknown probability fail or exclude |
| Frozen comparison family | Blocking | Policy validation tests | Baseline, full candidate and one declared ablation per component; all eight outcomes fixed |
| Authority separation | Blocking | Artifact and CLI tests | No study execution, promotion or routing authority |
| Delivery quality | High | Ruff, Pyright, focused/full tests, package smoke | Standard repository gate passes |

- Maximum evidence-changing passes: four
- Provider/spend ceiling: zero calls and USD 0
- Pass rule: all blocking rows pass; focused branch coverage remains at least 85%; full
  repository gate passes
- Escalation trigger: real signer custody, sampling design, rubric approval, holdout
  access, provider spend or statistical-method change
- Stop rule: implementation gates pass and missing real evidence is reported, not fabricated

## Iterations

| # | Slice | New evidence | Finding | Correction/result |
|---:|---|---|---|---|
| 1 | Contract and CLI implementation | Existing authenticated adjudication cannot attest pre-study ground truth | G3-C-001 blocking | Add a separate Ed25519 domain and metadata-only paired label claims |
| 2 | Focused negative tests | Missing-label and sampling probabilities could otherwise disappear | G3-C-002 high | Keep disagreements and unknown probabilities in explicit exclusion inventory |
| 3 | Policy completeness review | Optional ablations could be removed after results | G3-C-003 high | Require exactly one declared leave-one-component-out arm, including unavailable arms |
| 4 | Provenance and privacy review | A serialized inventory could be substituted before policy sealing; readable case/group identifiers could expose held-out label linkage | G3-C-004 blocking; G3-C-005 high | Replay signatures and eligibility from catalog/trust inputs; require opaque SHA-256 case/group references |

## Finding disposition

| ID | Consequence | Disposition | Acceptance check |
|---|---|---|---|
| G3-C-001 | Result grading could be mistaken for independently established ground truth | Resolved with separate claims/trust verification | Tampered, untrusted and same-key claims fail closed |
| G3-C-002 | Selective or missing labels bias the eligible sample | Resolved for recorded metadata; upstream completeness remains external | Exclusions retained; unknown probabilities never eligible |
| G3-C-003 | Post-hoc arm deletion biases incremental-value conclusions | Resolved structurally | Exact ablation family validator and unavailable-arm receipt |
| G3-C-004 | A fabricated inventory could receive a valid policy seal without signed source replay | Resolved; the seal boundary now rebuilds the inventory | Substituted inventory fails provenance verification |
| G3-C-005 | Human-readable identifiers could reveal held-out label linkage without opening session payloads | Resolved at this boundary; any digest-to-session map remains outside the artifacts and CLI | Claims and inventories accept only SHA-256 case and independence-group references |

## Exit

- Stop reason: the offline sealing boundary passed every implementation gate; real
  production evidence remains external and was not fabricated
- Rubric result: every blocking implementation row passes; held-out content was not
  inspected; production evidence remains absent
- Full quality gate: Ruff and format checks pass; Pyright reports zero errors; 2,497
  source-tree tests pass with 4 skips and 89% total coverage; export verification and
  wheel/sdist build pass; 1,855 installed-wheel tests pass
- Final privacy-edit confirmation: focused Ruff/format pass; all 15 context-study and
  feasibility tests pass with 89% affected branch coverage; the installed-wheel run
  above used the final opaque-identifier implementation
- Remaining uncertainty: no real signed catalog, reviewed arm implementations/resource
  plan, physical grader-independence evidence or independent statistical approval
- Human/domain approval: pending
- Durable facts: contracts, CLI, tests, threat model, study guide, roadmap and project
  memory record the completed offline boundary and the truthful zero-label production
  inventory
