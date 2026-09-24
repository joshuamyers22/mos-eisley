# Agentic Verification Loop: G4 candidate execution admission and dispatch

## Objective and authority

- Requirement: roadmap G4; plan §§14.2.1, 15.7, 26.2 and 26.4.
- Outcome: one separately signed, exact, one-use offline candidate reviewer-test
  run after custody, controls, binding and current Git replay.
- Invariants: no unsigned candidate path, host test fallback, repository/VCS write,
  network, credentials, provider call, correction or acceptance; stale or duplicate
  attempts fail closed; failed candidate tests remain evidence but not authority.
- Risk class: high-risk authorization and untrusted-code boundary.
- Implementation owner: Codex under Joshua Myers's direction; accountable
  production approval remains Joshua Myers's decision.
- Starting revision: `3a121fe`, clean worktree.
- Selected guides/templates: Python Engineering Guide, Agentic Verification Guide
  and loop template, Threat Model, Adversarial Review Playbook and review template,
  Work Note.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Exact candidate authority | blocking | domain-separated enrolled creator signature and exact record/request/image links | substitution, wrong role or expired approval rejects before execution |
| One-use dispatch | blocking | exclusive private persistent claim | duplicate/concurrent attempt rejects; claim survives failure |
| Source and execution containment | blocking | current read-only Git replay, isolated worker and post-run checks | dirty/stale source or image mismatch rejects; no host fallback |
| Honest result | blocking | exact count receipt and claim replay | passing/failing candidate distinction retained; neither grants correction/acceptance |
| Delivery | high | focused/full tests, static gate, build and installed wheel | no unresolved new code failure or live calls |

## Budget and stopping rules

- Maximum iterations: one implementation plus two evidence-changing review passes.
- Elapsed/cost ceiling: this offline session; zero provider spend.
- Pass rule: all blocking rows pass; expected environmental failures are identified
  and separately reconciled, never called passing.
- Diminishing-return/abort: stop on no new evidence, a failed boundary, an
  unreconciled full gate or a need for real key custody/production authority.

## Iterations

| # | Implemented slice | New evidence/context | Finding and correction | Gates |
|---:|---|---|---|---|
| 1 | Separate signed approval, current Git preflight, one-use claim and isolated dispatch | Real Git fixture, actual worker observation, wrong-key/window/stale-tree/replay cases | Generic runner bypass found and closed | Focused candidate tests pass |
| 2 | Private claim replay, library location checks, CLI path and post-run drift | Tampered claim, private-store mode, full CLI check/dispatch/verify and spent-claim drift | Claim and path findings closed | 41 focused G4 tests pass |
| 3 | Complete source gate, unrestricted loopback reconciliation and wheel build/smoke | 2,471 source tests; 48 localhost tests rerun; two full wheel attempts plus isolated installed-wheel modules | No G4 regression; full installed-wheel smoke remains non-green in review fixtures under suite load | Static/export/build pass; 41/41 installed G4 tests pass; full smoke blocked |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Disposition and acceptance check | Owner |
|---|---|---|---|---|---|
| G4-CE-001 | generic isolated runner previously accepted candidate role | bypass signed approval | high | accepted; generic runner rejects before container call | Joshua Myers |
| G4-CE-002 | receipt claim was not checked against stored bytes | false one-use evidence | high | accepted; exact private claim replay and tamper regression | Joshua Myers |
| G4-CE-003 | direct library caller could put state under Git | repository contamination | medium | accepted; library location guard before dispatch | Joshua Myers |

## Exit

- Stop reason: offline G4 implementation and focused/package-specific verification
  passed; stop before production use because the complete installed-wheel smoke gate
  remains non-green and accountable owner review is still required.
- Rubric result and blocking findings: exact authority, one-use, containment and
  result rows pass the targeted evidence. Delivery row is unresolved at the full
  installed-wheel suite level; no G4-specific failure reproduced.
- Full quality-gate command and result: `make check` passed Ruff and Pyright,
  then ran 2,471 source tests with 31 sandbox-denied localhost errors and four
  skips. The affected MCP HTTP/OAuth/schema modules passed 48/48 with loopback
  permission. `make verify-export build` passed. The first `make smoke` was blocked
  by sandbox DNS; approved retries installed the locked wheel but the 1,787-test
  run had two review-fixture errors, and the expanded 1,827-test run had two errors
  plus one launch-admission verdict failure. An added post-run drift regression
  passed after these broad runs. Installed-wheel G4 tests passed 41/41;
  installed-wheel launch-admission passed 24/24 and conformance-acceptance 14/14
  when isolated. These passing modules do not turn the full smoke gate green.
- Production-like replay/fault evidence: disposable real Git and local worker, plus
  injected Docker response; no actual production candidate execution. Wheel CLI
  exposes the new commands and its G4 regression modules pass from the installed
  artifact.
- Remaining uncertainty: local clock/store, same-UID host, Git, Docker, image and
  source-to-dependency correspondence are trusted; physical signer custody,
  meaningful test adequacy, correction and independent final review remain open.
- Human/domain approval: not performed for production use.
