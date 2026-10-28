# Review-conformance fixture reliability repair

- Status: fixture repair and combined quality gate complete; candidate unpublished.
  Owner: Joshua Myers; operator: Codex. Started 2026-10-28.
- User requested fixing the fixture failures that block the existing rc.10
  watchdog batch in this worktree. Preserve all existing changes and failed logs.
- Existing source-gate failures: missing verified critic quorum during launch
  fixture setup, and missing judge `runtime-count-start.json` during tranche
  fixture setup. Isolated coverage reproductions passed. Cause is unconfirmed.

## Objective, invariants and budget

Identify the actual failing stage before temporary fixture cleanup, make the
smallest evidence-backed fixture correction, and verify the affected acceptance,
launch and inherited campaign tests. Production authorization, quorum, receipt
requirements, deadlines, one-use claims and spending remain unchanged. Never
fabricate missing runtime receipts or replace an actual failed result with success.
Use synthetic test transports and keys only; zero provider calls or sampling-store
access. Preserve the original failures from the watchdog work note.

Selected guidance: AGENTS/CONTRIBUTING, Python Engineering Guide, Agentic
Verification Guide, adversarial review playbook, work-note, threat-model and
verification-loop templates. The project brief and existing memory establish
the evidence/authorization boundaries. No independent or owner release approval
is asserted by this test repair.

Bound one diagnostic capture, at most 30 repeated synthetic fixture setups or
10 minutes, stopping at the first captured failure; one deterministic reproducer
and correction, then affected fixture families and a combined `make check`.
Each full gate has a four-hour ceiling. Stop on new unexplained failures and
retain diagnostic metadata, rather than retrying broad suites without new evidence.

## Acceptance rubric

| Boundary | Required evidence |
|---|---|
| Root cause | Controlled failing-stage capture or deterministic reproduction |
| Fixture reliability | Corrected test reaches intended acceptance boundary under the triggering condition |
| Evidence integrity | Real fixture receipts verified; missing/changed receipts still refuse |
| Production policy | No weakened quorum, grants, spending or deadline behavior |
| Batch verification | Focused/inherited fixtures, static checks and combined gate pass |

## Observations

- The bounded diagnostic completed 30 original synthetic setups under coverage
  in 117.851 seconds, with no failure captured. The discarded historical OS or
  transport exception cannot be reconstructed from the retained broad-gate logs;
  no exact historical cause is claimed.
- An initial in-process exchange experiment did not fix inherited fixtures:
  67 campaign cases had three errors; 62 launch cases had two failures and two
  errors. Immediate approval construction could already report expiry, before
  worker startup. The experiment and its helper were removed. These failed logs
  remain preserved; no passing claim is made for that approach.
- The correction supplies one UTC anchor plus real monotonic elapsed time to
  each synthetic acceptance case and its inherited campaign/launch cases.
  Scoped patches cover loaded datetime consumers and restore after each case;
  stdlib datetime, event-loop time and production source remain unchanged.
  Elapsed time still advances and policy durations are not enlarged.
- A controlled UTC jump between judge admission checks reproduces an
  infrastructure-error result with no judge runtime-start receipt. With the
  shared fixture clock, the same real-pipe review completes and verifies its
  actual receipts. Deleting the receipt still refuses collection. This proves
  the failure mechanism, not that an OS clock jump caused the historical runs.
- Five new regressions cover forward/backward wall jumps, shared clock and
  cleanup, real-pipe success and missing-receipt refusal, the controlled failure,
  and unchanged signed-grant rejection after elapsed expiry. All five pass;
  focused Ruff/format and strict Pyright pass. Under coverage, 15 acceptance
  cases (61.224 seconds), 67 campaign cases (240.318 seconds) and 62 launch cases
  (296.984 seconds) pass.
- Fixture construction now accepts the running test case as cleanup owner;
  manually instantiated async test cases are not used to own clock patches.
  Setup also reports infrastructure errors before trying to collect receipts.
- The clean-wheel whitelist includes the clock helper and its regressions, so
  installed-wheel verification exercises the same test fixtures.

Private diagnostics remain under `.work/watchdog-verification/`; no request or
response payload or bearer capability belongs in this note. No production review
or watchdog source changed in this fixture repair. Existing watchdog native
artifacts remain bound to their original verified runtime-input manifest.

## Final verification and disposition

The combined `make check` passed on this watchdog/fixture batch:

- Ruff lint/format and strict Pyright: pass, zero type errors or warnings.
- Source: 3,887 tests in 2,904.927 seconds, 17 skips; coverage 86%.
- Frozen runtime export verification and wheel/sdist builds: pass.
- Installed wheel: 2,862 tests in 2,042.404 seconds, 13 skips; pass.

The original failed gates and rejected in-process experiment remain failures.
No exact historical clock or transport fault is asserted. This repair removes
wall-clock discontinuities from synthetic fixture aging while preserving actual
elapsed expiry and real-pipe receipt requirements. No production review logic,
provider configuration, subscription allowance or release approval changed.

Private evidence under `.work/watchdog-verification/`:

| Record | SHA-256 |
|---|---|
| `fixture-repair-inputs.json` | `0d38bb86a6a009a89a20d3f5ae37aede22fd75188284dc729896624538eba967` |
| `make-check-fixture-repair.log` | `cbf72a6397e5ef8538cdbd767bc3ed4d686bf24e156a977c66d2ef7540f49d75` |

All 12 executable/test inputs match their pre-gate hashes. Documentation-only
result updates follow the gate; no executable contract changes follow it.
The tested batch remains on `fix/frozen-watchdog-dispatch` for review. Exact-source
protected signing, four-target native qualification and fresh installed live
qualification remain release work; this gate does not publish rc.10.
