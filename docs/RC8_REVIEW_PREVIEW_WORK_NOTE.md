# rc.8 review integration and preview qualification

- Status: local qualification passed; protected integration and exact native/signed CI pending
- Owner: Joshua Myers; implementation and technical verification by Codex
- Started: 2026-10-23 UTC; updated: 2026-10-24 UTC
- Branch: `release/review-platform-preview`
- Inputs: main `f31b4dd`, review/platform `8cef1b4`, startup `d3b5357` (PR #325)
- Review by: next preview disposition

## Objective and authority

Joshua requested closing and integrating the existing review/platform work, then
qualifying a new preview. Preserve its nine commits and combine them with current
main and startup diagnostics in an isolated worktree. Existing worktrees/edits
remain untouched. Prepare `0.1.0-rc.8`; publication, stable launch, provider
activation and studies remain separate decisions.

Guidance: AGENTS.md/CONTRIBUTING.md, Python engineering guide, agentic verification
guide/loop template, adversarial playbook/review template, threat model and release
checklist. Retrieved README, brief/memory, roadmap, plan §§27–29 and 31.5–31.7,
credential-boundary threat model, scoped/managed-worktree review records, recovery,
startup investigation, publisher runbook and actual workflows.

## Scope and invariants

Material integration with high-risk optional credential and release-compatibility
boundaries. Keep native credential attachment opt-in, exact live admission,
source freshness, structural critic/judge isolation, quorum, one-use spending,
cancellation and uncertain-effect recovery. No real credentials, sampling stores,
provider inference or owner-state mutation are needed. Preserve immutable releases.

The preview targets macOS/Linux ARM/x86. Narrow WSL2 read-review qualification
cannot establish general WSL2, native Windows, Apple notarization/cask or stable
support. The candidate includes scriptable execution, durable recovery, ranked
resume, scoped live review, managed-worktree reads and startup diagnostics.

Bound: one coherent full local gate plus evidence-backed affected corrections;
maximum two correction passes per new failure, four hours per combined native
gate, standard runner labels and zero model spend. Stop on failed mandatory
checks, signature/source/state mismatch or unavailable accountable approval.
Earlier interrupted/failed attempts are never counted as passing. Revert the
integration to restore source; never retarget immutable tags or strip journals.

## Compatibility finding and correction

The untouched public rc.7 installed in an isolated root rejected source-candidate-
written snapshot and SQLite sessions: both writes succeeded, both old readers
exited 2 with invalid schema. A sandboxed attempt could not initialize the frozen
loader semaphore; the permitted native run supplied the actual result. This
confirms the old-reader limit already documented in session-recovery verification.
The missing release storage-epoch fence would have allowed incompatible rollback.

[ADR 0019](adr/0019-recovery-release-storage-epoch.md) proposes epoch 2. Default
candidate/publication parsing stays current-epoch-only; explicit retained metadata
inspection preserves authenticated legacy epoch identity without installation
power. Current-epoch install/discovery and rollback's equal-epoch guard prevent
unsafe downgrade before pointer/data mutation. No journal, grant or ledger is
rewritten. Preserve compatible readers and separate pre-upgrade private copies;
new data uses forward fixes. Accountable release disposition remains pending.

The predecessor harness retains successful candidate-written-state rollback for
same-epoch pairs. Cross-epoch pairs must prove explicit refusal, unchanged current
runtime/data, candidate continuation, real activation-interruption recovery,
legacy-reader rejection, separate old recorded-copy readability and both uninstalls.
Reports distinguish those results and explicitly deny seamless rollback.

## Verification record

| Check | Result and scope |
|---|---|
| Historical native review | Run [39881254556](https://github.com/joshuamyers22/mos-eisley/actions/runs/39881254556) passed exact `8cef1b4` on Linux and actual Windows-hosted WSL2: 3,853 source/2,831 wheel tests (17/13 skips), 116 focused cases per mode with no skips; matching 413-file wheel/host identities checked. Separate current-candidate gates remain. |
| Combined focused boundaries | 134 tests passed: credential sockets, managed-worktree/scoped review, ranking, recovery, startup and four earlier failed review fixtures. |
| Metadata/package correction | 64 tests passed, including explicit legacy metadata inspection, cross-epoch refusal/data preservation, incompatible discovery and legacy-signature publication refusal. |
| Publication/report tooling | 14 publication and five native-report validator tests passed; the rc.7 output-name regression caught and corrected accidental rc.5 evidence-path reuse. |
| Provisional native Mac | Self-contained development build passed exec/cold resume for both stores, committed recovery metadata, setup, tamper/refusal, interruption/recovery and state preservation. Ephemeral publisher only; dirty-worktree provenance is not an exact release artifact. |
| Awake full source | 3,874 tests in 2,878.064s; 17 platform skips; 86% coverage. Lint/format, strict typing, export verification and builds passed. |
| Awake full installed wheel | 2,851 tests in 2,041.355s; 13 platform skips. |
| Original audit | Failed on setuptools 84.0.0, GHSA-xmj3-9gf7-h52w; no vulnerability suppression. |
| Security correction | Only transitive setuptools upgraded to 84.1.0; runtime export refreshed. Direct audit reports no known vulnerabilities/adverse statuses in 54 packages. Application code unchanged. |
| Fixed-lock package gate | Passed: 64 focused package tests, lint/format/strict typing, export verification, fresh build, 2,851 installed-wheel tests in 2,157.459s (13 skips), and clean audit of 54 packages. Application source is unchanged; final CI rechecks full source on the fixed lock. |
| Current native/signed CI | Pending exact committed candidate, four native targets, Linux/WSL2 evidence and enrolled-key signed predecessor qualification. |

## Failed/interrupted attempts and limits

The startup-only branch's earlier local run passed 3,810 source tests but failed
four wheel fixture setups; its GitHub checks passed independently. The original
empty-start exit causes remain unknown. This work adds diagnostics, not an
unreproduced runtime fix.

The first integration gate was interrupted on the actual compatibility finding.
A subsequent source run completed 3,873 tests in 2,956.034s with five failures,
twelve errors and seventeen skips, without reaching wheel/audit. Wall age jumped
overnight; power logs confirm maintenance sleep/dark-wake cycles. Expired approvals,
quorum and incomplete downstream evidence are consistent with suspension, not proof
of every cause. All seventeen exact cases passed in 42.081s under bounded
process-only sleep prevention before the successful full source/wheel run.
No timing, quorum or spending assertion was relaxed.

A final static check caught a no-op cast after parser separation; it was removed,
then the complete final-code lint/format/typing stages passed. The combined awake
run remains an audit failure until the separate security correction is validated.
Disposable logs/captures stay ignored in `.work/`; no raw payloads enter Git.

## Native and publication contract

The published rc.7 is immutable release ID `421278021`, source `78bc17c`.
Retain rc.1/rc.2/rc.3/rc.5 journeys and add actual rc.7-to-candidate qualification.
Its Intel job used 36m15s with four predecessors. Allow 75 minutes for five pairs
plus new epoch-transition/refusal/backup checks; retain all targets/assertions.
This is a CI ceiling, not product authority. Native installer smoke now exercises
real frozen exec/recovery for both stores and requires one committed final result.

The historical rc.1/rc.2-only workflow checks out its existing pinned epoch-1
`CANDIDATE_SOURCE` (`c090592`) for its harness/manifest. Existing exact-run/source
checks remain; it does not apply current epoch-2 policy to historical binaries.
Six newer dependency-bot PRs were observed on 2026-10-24; they remain separate.
Only the mandatory audit fix joins this candidate.

## Handoff and disposition

Complete the fixed package gate, preserve all source commits, publish a reviewable
PR and require final-head protected CI plus native evidence before integration.
Then freeze a mainline tag matching metadata, qualify exact signed artifacts and
actual predecessors, and retain owner data/immutable releases. Protected signing
and publication require accountable owner disposition; agent technical review
is not independent security or release approval. See
[the technical review](RC8_INTEGRATION_REVIEW.md).

The fixed-lock tested wheel is `mos_eisley-0.1.0rc8-py3-none-any.whl`, SHA-256
`9161df55226638717de1a9b96ea8819f8158df1ff263b4cea3d3c827db7609e7`.
All 414 packaged Python files match current source bytes. This is local package
qualification; committed native and signed-release artifacts remain separate.
The delivery PR validation section is the current record of final-commit CI.

## CI follow-up: historical metadata custody

The first PR run `40134756097` failed the historical rc.1/rc.2 jobs at their
unchanged source-identity guard. Selecting old harness `c090592` also selected
its older signed metadata (`d8b05ad`), while the reviewed current metadata binds
artifact source `8ef4e62`. Preserve the current signed bytes in runner temporary
storage before checking out the epoch-1 harness, then copy those same bytes into
the candidate directory. Do not alter signatures, archives or expected source pins.
A regression checks actual metadata/source agreement and copy/checkout ordering.
All 65 affected package/publication tests and static checks pass. Application
source and the tested wheel's 414 Python files are unchanged; new exact-commit CI
repeats the affected native evidence.

## WSL2 follow-up and owner dependency selection

Joshua selected #333's tested dependency set for rc.8; #332's already merged
SDK/HTTP changes are integrated separately on current main. This candidate
retains its lock (including the setuptools audit fix).

At `dac047c`, all 21 other GitHub checks passed, including Linux review, full
source/package quality, four development distributions, both development
Homebrew checks and four historical-upgrade jobs. The four native reports bind
PR merge `de0cfb3`, whose tree equals `dac047c` tree `a862c7c`; all record exec
recovery for both stores, zero paid calls and an ephemeral test publisher. They
are not enrolled-key signed qualification.

WSL2 run [40135543137](https://github.com/joshuamyers22/mos-eisley/actions/runs/40135543137)
failed after 3,875 source tests (two failures, 17 skips). One unsafe-directory
fixture reproducibly became mode 0700 under the harness's umask 077; explicitly
chmod its deliberately unsafe directory to 0755, matching existing fixtures.
The other single-turn subscription fixture returned 2 with no retained diagnostic
in the assertion; its root cause is unknown. Preserve receipt filenames and
fixture-invocation presence in that assertion. Do not weaken runtime timeouts,
assertions or permissions. Both affected suites pass all 43 cases under umask
077; repeat exact native CI on the correction. Failed WSL2 evidence remains a
failure until a new complete gate passes. Application/lock bytes are unchanged.
