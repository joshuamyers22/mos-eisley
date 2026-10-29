# Source-bound coding test execution receipts

- Status: local source/integration gates passed; protected integration, signing and
  fresh installed qualification pending. Owner Joshua Myers; operator Codex.
  Started and last updated: 2026-10-29 UTC.
- New candidate: rc.11, based on immutable rc.10 source 9ffd540; published rc.10
  and all failed campaign/usage records stay unchanged. Keep frozen dependencies
  and storage epoch 2; main's newer dependencies remain separate.

## Objective, guides and threat boundaries

The owner requested concrete test execution receipts in a new candidate, then
repeat affected qualification. RC10-SUB-02's implementation review could see only
hashes/pass, despite internal worker completion checks. Expose versioned bounded
execution details tied to the exact source/test hashes and selected test paths.
Use Python engineering, bounded verification guide/loop, work-note and threat-model
instructions from the production template, plus existing release/install contracts.
Risk: untrusted test output and worker evidence crossing the review/integration
boundary. Native credentials remain client-owned; no API fallback, credit purchase,
model substitution, raw test output disclosure or retroactive evidence repair.

Historical four-field verification records must retain their canonical bytes and
remain readable. Recorded CodingHandoff deliberately projects to its existing
four-field verification before storage; rich execution receipts remain in worker
and live review artifacts. No stored handoff schema/epoch change is introduced. New live execution requires concrete receipts before reviewers
or integration; missing, contradictory or substituted receipt identities refuse.
Report selected files, tests/failures/errors/skips, runner success/exit status,
post-run file integrity, combined output byte count and digest. Preserve no-skip,
nonempty-test, output/deadline/descendant cleanup and protected test invariants.
Bound combined stdout+stderr to 32000 bytes. Raw output remains private/hashed.

## Rubric and budget

Focused worker/domain/live tests must prove real passing/failing tests, wrong or
missing/duplicate records, combined output bounds, count/schema/path/identity
refusals, historical byte compatibility, both-store review packet propagation,
and refusal before model dispatch/integration for missing evidence. One combined
full make check on frozen candidate before commit/PR, four-hour gate ceiling;
focused corrections only when a new defect supplies evidence. Required CI and
normal main integration precede exact tag signing; no admin bypass or tag changes.
Build a fresh immutable offline image containing the changed worker; the prior
rc.10 image cannot supply new receipts. Sign through protected custody, repeat all
four signed installed/guardian and predecessor checks, then a fresh macOS arm64
installed subscription campaign on both stores. Publication awaits evidence/owner
review; no stable/full-v1 or conversational /review claim.

One fresh subscription campaign: 14 invocations/store, 28 total, one-hour scopes,
90-minute global ceiling, 60-second native deadlines, 8192 reported output tokens,
16000 text bytes, 128000 canonical input bytes, 600-second coding walls, zero
correction cycles. Use the previously selected exact client/model profile and
fresh verified readiness after gates; no authorization renewal/replay or retry
following the first unplanned failure. Native billing/retries remain unverified.
Stop globally on any unexplained signature, source, test, provider, review,
integration or cleanup failure; preserve failed evidence and unused capacity.

## Handoff

Implementation, focused verification, actual rebuilt-worker proofs and both full
local gates passed. Commit the unchanged frozen source, establish protected main
ancestry through the normally reviewed integration, then build/sign and qualify
the exact tag. No signed rc.11 or fresh live acceptance is claimed yet.

## Verification observations

- Focused checks passed: 14 worker cases, 19 recorded-controller cases, 24 live
  workflow cases, 42 distribution cases and 15 frozen publication contracts
  (16 on main, retaining its separate predecessor-attempt contract). Strict
  Pyright and Ruff passed on the frozen source; main's Ruff/format also passed.
- Initial pre-report-fix rebuilt local worker image:
  `sha256:05493e168445aa9c17a1295ea07724f06ab2ba9c5e6cc2530f1e17773345bbd2`.
  All installed Python source hashes matched the frozen candidate. Two actual
  workers returned expected baseline failure and three passing candidate tests,
  concrete receipts and armed/lease-bound cleanup. Exact containers were absent;
  provider calls were zero. This is not yet a signed-native qualification claim.
- Before the report-digest correction, an additional actual signed rc.10 reader passively reopened newly generated
  recorded handoffs on both snapshot/SQLite without changing storage or replaying
  provider/worker work. Its state codec also accepted the new canonical record.
  The retained four-field handoff projection preserves epoch-2 compatibility.
  Review digest: `a6f2e6284cabbb027c35abec52de1955c6fffc1dbe873a76ac17ff7f72486396`.
- Disposable helper setup failures are retained: the first worker proof constructed
  an inconsistent multi-file synthetic brief before worker/provider dispatch;
  the initial previous-reader harness incorrectly selected inspection instead of
  passive resume. Corrected unpaid helpers used separate evidence roots, with no
  source/test changes, paid retry, failed campaign replay or evidence replacement.
- Full frozen candidate and main-integration gates run against hashed inputs.
  Main retains its newer dependencies; exact merge provenance and input equality
  will be verified after the frozen candidate gate permits committing its source.
- The first full candidate gate was launched inside the outer sandbox and failed
  native environment checks: 3,892 source tests, five failures/104 errors/17 skips,
  with explicit localhost-bind denials, unavailable nested OS Git isolation and
  tmux refusal. Main's similarly restricted run was stopped with SIGINT (exit -2).
  Both logs/results remain retained as nonpassing evidence. A focused two-case
  native Git-confinement preflight passed outside the outer sandbox. Both full
  gates were relaunched there against unchanged input hashes; no source changes
  or test suppression were used to correct the execution environment.

- Compatibility inspection reproduced a report digest referencing the richer
  transient verification rather than the four-field retained handoff. The
  recorded controller now hashes the retained verification; a regression assertion
  verifies its evidence reference after loading both stores. Both focused recorded
  controller runs passed 19 cases; strict type checking passed. Native full gates
  were interrupted before the two-file correction; those partial runs are retained.
- Final rebuilt image: `sha256:e3543e68d9dfdc9a198d02a4669d243d9093d41704116afcc35f9af011735661`.
  Exact installed source, expected baseline failure, three passing candidate tests
  and two lease-bound guardian cleanups passed on this image, with zero providers.
  Actual signed rc.10 passive resume/unchanged storage passed again on both stores
  with the corrected retained report digest. Final compatibility review digest:
  `a6f2e6284cabbb027c35abec52de1955c6fffc1dbe873a76ac17ff7f72486396`.

## Final combined local gates

| Tree | Source suite | Installed-wheel suite | Coverage | Full elapsed |
|---|---|---|---|---|
| Frozen rc.11 candidate | 3,892 in 3,064.837s; 17 skips | 2,867 in 2,356.364s; 13 skips | 86% | 5,487.095s |
| Main dependency integration | 3,894 in 2,987.836s; 17 skips | 2,879 in 2,303.243s; 13 skips | 86% | 5,357.326s |

Both complete `make check` gates returned zero, including Ruff/format, strict
Pyright, export verification, build and installed-wheel smoke. All 856 candidate
and 857 integration non-Markdown inputs match their frozen manifests; final
validation checked exact file sets as well as contents. Both gates are within
the four-hour ceiling. The earlier sandbox failures and pre-report-fix
interruptions remain nonpassing historical records.

Final frozen log SHA256:
`b6121e950280b4dcd17237457420ab5ad8a2c90c24d87f0c2098d29405bf37b1`.
Final integration log SHA256:
`68b1d4c6f7aceb11238e63b568301bb6675f6907f725e40d0494bae26078a36f`.

Before the integration commit, the actual normal merge must reproduce the tested
non-Markdown inputs exactly while preserving main's newer dependencies and
current documentation. Required PR CI and verified ancestry precede tag creation.

## Main integration provenance

Frozen source `4d927cea23ff18f6aa9d231f7c342ee8e2420c84` was committed and
pushed only after its complete gate passed. A normal merge into main's current
documentation head `b534c3bd409418181eb7d107717c1df77fe5b8e1` preserves that
source as a parent. Main's newer dependency set remains intact. The predecessor
allowlist overlap retains both rc.9 and rc.10; the memory index retains main's
current rc.10 evidence and the new receipt row. All 857 non-Markdown file names
and content hashes exactly match the passed integration gate before committing.
No signing or new native inference has occurred yet. Required PR CI/merge and
local ancestry verification precede tag creation.
