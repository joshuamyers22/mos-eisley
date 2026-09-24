# Agentic Verification Loop: G4 bounded correction evidence gate

## Objective and authority

- Requirement: roadmap G4; plan §§14.2.1, 26.2 and 26.4; loop plan L2/L3.
- Outcome: only a reproducible, signed implementation-defect finding can claim
  one of two offline correction cycles; a renewed chain is required afterward.
- Invariants: no child/provider dispatch, repository/VCS write, test weakening or
  acceptance; all findings and aggregate allowances remain visible across cycles.
- Risk class: high-risk authorization and untrusted-test evidence boundary.
- Implementation owner: Codex under Joshua Myers's direction; production approval
  remains Joshua Myers's decision.
- Starting revision: `62bdcd1`, clean worktree.
- Selected guides/templates: Python Engineering Guide, Agentic Verification Guide
  and loop template, Threat Model, Adversarial Review Playbook and review template,
  Work Note.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Reproduced implementation violation | blocking | two approved receipts, matching schema-2 IDs/counts, signed full-ID judge triage | errors, drift and non-code dispositions deny cycle |
| Exact bounded authority | blocking | enrolled creator signature, path/child/revision/test links, fixed deadline and aggregate allowances | stale, forged, expanded or exhausted grants deny before claim |
| Durable cycle state | blocking | private exclusive claim/completion and carried previous hash | duplicate, concurrent, forged predecessor or third cycle deny |
| Corrected result | blocking | renewed custody/Git/candidate chain, unchanged plan/creator-suite approval hashes and exact reviewer test/adapter/static inputs | passing result remains non-accepting |
| Delivery | high | focused/full source checks, export/build, installed wheel | no unreported skips or failures |

## Budget and stopping rules

- Maximum iterations: implementation plus two evidence-changing review passes.
- Elapsed/cost ceiling: offline session, zero provider spend.
- Pass rule: all blocking boundaries have focused positive and negative evidence;
  full gate status is reported separately.
- Abort/escalate: failed authority boundary, unreconciled full gate, or need for
  accountable signer/critic/production approval.

## Iterations

| # | Implemented slice | New evidence/context | Finding/correction | Gates |
|---:|---|---|---|---|
| 1 | schema-2 worker failure IDs and signed triage | actual isolated worker plus distinct candidate receipts | count-only receipts could not identify an exact finding; corrected | focused G4 tests |
| 2 | private cycle claim, fixed aggregate allowance and renewed-chain completion | real Git, forged signature/completion, duplicate and second-cycle fixtures | predecessor needed persisted completion; corrected | focused correction tests |
| 3 | CLI and installed-wheel inclusion | package command surface; 2,476-test source suite, unrestricted MCP reconciliation and clean installed wheel | sandbox loopback/DNS denials separated from product failures | Ruff/Pyright, 4 focused correction and 16 related G4 tests, export/build and 1,832-test wheel smoke pass |

## Finding disposition

| ID | Location/evidence | Consequence | Severity | Disposition and acceptance check | Owner |
|---|---|---|---|---|---|
| G4-BC-001 | prior observation had only failure counts | could not bind a correction to a test identity | high | accepted; schema-2 failed IDs and exact two-run match | Joshua Myers |
| G4-BC-002 | initial cycle history could be supplied without a stored completion | bypass across restart | high | accepted; private completion replay before cycle two | Joshua Myers |
| G4-BC-003 | per-cycle bounds alone reset total allowance | excess correction allocation | high | accepted; fixed signed task ceiling and carried worst-case reservations | Joshua Myers |

## Exit

- Stop reason: offline boundary and clean-wheel verification pass; stop before
  production child dispatch or acceptance, which need separate gates and owner review.
- Rubric: focused authority/cycle/renewed-chain checks and installed artifact
  pass. This is not production approval.
- Full quality gate: `make check` passed Ruff and Pyright, then ran 2,476 source
  tests with 31 localhost-bind `PermissionError` cases and four skips in the
  sandbox; it stopped before export/build/smoke. The affected MCP pattern passed
  68 tests with loopback permission (four skips). `make verify-export build`
  passed separately. `make smoke` first failed on sandbox DNS; with network
  permission, a clean environment installed the locked wheel and ran 1,832 tests
  successfully. The installed-wheel pass does not erase the sandbox-only source
  gate exit code, which is reported above.
- Production-like replay: disposable real Git repository and isolated worker;
  provider/model correction dispatch was not run.
- Remaining uncertainty: critic artifact is hash-bound but not authenticated by
  this gate; semantic citation aptness, signer custody, trusted external time,
  actual spend, correction dispatch and final
  independent review remain open. Creator-test file blobs are not replay-compared
  by this controller; the claimed suite digest is not a replacement.
- Human/domain approval: not performed for production use.
