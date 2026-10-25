# rc.8 signed candidate and installed qualification

- Status: closed; prepublication review blocks the four-target preview
- Owner: Joshua Myers; qualification and technical review by Codex
- Started: 2026-10-25 UTC
- Review point: exact candidate evidence before any publication decision
- Frozen source: `eadb415d31afd89b142e3229a8ccca72aca835ee`
- Integrated main: `b5d2c766bafca7ce17eac5c9e7b92fb23eb297bb`
- Existing tagged workflow: [40217716964](https://github.com/joshuamyers22/mos-eisley/actions/runs/40217716964)

## Objective and authorized scope

Build and sign the exact frozen candidate through the protected workflow; qualify
signed installation and actual rc.1/rc.2/rc.3/rc.5/rc.7 predecessors on macOS/Linux
ARM/x86; exercise unpaid installed snapshot/SQLite execution, cold resume,
terminal/diff and recovery; review the evidence before publication.

The user authorized these qualification steps. Signing preparation may proceed
through its existing approval gate. The separate publication job remains
unapproved. No provider inference, study, credential enumeration, owner-state
mutation or signing-key extraction is part of this work. Preserve immutable tags,
archives, journals, usage history and prior failed evidence.

## Retrieved contracts and selected guidance

Repository AGENTS/CONTRIBUTING, README/brief/memory, ADR 0019, publisher runbook,
release workflow and native/upgrade harnesses, and the installed-v1 matrix/runbook
prepared in the separate readiness worktree. Use the existing Python engineering,
bounded verification, threat-model and adversarial-review guides/templates and
release checklist. No update to the frozen source or its dependency lock.

## Verification contract

High-risk signing/compatibility qualification. One exact tagged preparation plus
four signed native jobs; supplemental unpaid installed checks against the same
artifact identities. Four hours per combined native gate; at most two corrections
per new harness failure, with failures retained. Zero provider spend. Stop affected
work on identity/signature/source mismatch, failed mandatory check, state loss,
uncertain side effects or exhausted declared limits. Never relax a product guard
or retarget an immutable tag to make a check pass.

| Blocking dimension | Acceptance evidence |
|---|---|
| Identity and supply chain | Exact source/tag/main ancestry, frozen lock, complete prepare checks/audit, source/SBOM/checksum files and enrolled-key metadata |
| Installation | Four exact signed native jobs, no external runtime or provider keys, immutable archive/bootstrap hashes |
| Actual predecessor compatibility | Five real predecessors per target; both stores, epoch-2 upgrade, 2-to-1 rollback refusal, unchanged pointer/state, legacy backup readability and old-reader refusal |
| Installed behavior | Both-store exec/stdin/result integrity, cold resume, actual terminal/PTY and diff/stale-source behavior, cancellation/recovery and preserved state |
| Publication boundary | Separate publication approval withheld; final evidence inventory and accountable disposition distinguish preview qualification from full v1 launch |

## Observations and attempts

- Existing annotated `v0.1.0-rc.8` resolves to the requested frozen commit. Its
  Git tag is unsigned; application authenticity comes from the enrolled Ed25519
  metadata in protected preparation, not a claimed Git tag signature.
- The release run was already active on that source. Reuse it; do not start a
  duplicate build/signing campaign. Three native development jobs and gitleaks
  passed at initial inspection; Intel was still running and signing had not begun.
- `application-release` disallows administrator bypass and has a separate required
  approval for prepare and publish. Approval will be scoped to preparation only.
- The guarded prepare-approval attempt observed that the job had already advanced
  to running; its precondition stopped before sending an approval. No duplicate
  approval or publication approval was issued by this task.
- Four native development builds passed. Protected preparation is running its
  mandatory `make check audit` on the frozen source/lock.
- Supplemental external-CLI tooling lives only on
  `test/rc8-installed-qualification`, separate from the immutable candidate. Its
  read-only four-target workflow downloads the exact protected run's signed
  artifact; it has no signing/publication environment or write permission.
- Three identity/result negative tests, Ruff/format and strict Pyright passed.
  Real development-binary PTY checks passed on snapshot and SQLite. The first
  helper attempt failed to match a differential screen repaint; requesting a
  full repaint before matching contiguous text corrected the harness without
  changing product behavior or assertions. Signed checks will repeat this path.

## Verification results

- Protected prepare passed: 3,875 source tests run (17 skips), 86% coverage,
  2,851 installed-wheel tests run (13 skips), clean locked audit of 54 packages,
  container checks, SBOM and enrolled-key signing. Exact counts came from the
  completed prepare-job log, retained privately after sanitization for display.
- Four signed native jobs passed. All 26 receipts were cross-checked against the
  signed source/metadata/archive identities: four native installations, twenty
  actual predecessor journeys (five per target), two macOS generated-formula
  checks. All actual pairs are epoch 1 to 2 and prove refusal rather than seamless
  downgrade, separate old-backup readability and retained user state.
- Initial supplemental run 40229624329 passed both macOS targets and failed both
  Linux targets at Git isolation. It remains failed evidence. The follow-up
  [40230486519](https://github.com/joshuamyers22/mos-eisley/actions/runs/40230486519)
  preserves failed status while collecting both independent backends and a direct
  frozen-launcher diagnostic. Both macOS jobs pass; both Linux jobs fail.
- On all four targets/both stores, signed native exec/stdin, passive cold reopen,
  exact attempt/journal preservation, admitted follow-up, abrupt idle process-loss
  recovery and invalid-input refusal pass. Linux cannot acquire the required diff
  isolation; dependent terminal assertions remain unproven. Both macOS targets
  pass real PTY diff/attachment/stale-source, Unicode/paste/resize/draft and normal
  terminal restoration checks.
- Final helper identity/result tests, Ruff/format and strict Pyright pass.
  Documentation links, whitespace and evidence-manifest consistency were checked.
  Frozen product source, lock, tag, root metadata and native archives were unchanged.
- Final [prepublication review](RC8_PREPUBLICATION_REVIEW.md): **block** for
  RC8-Q01, the unsupported Python-module launcher invocation from frozen Linux.
  No bypass, source patch, tag rewrite, publication or provider call occurred.

Three transient log-read conditions were resolved without rerunning the release:
`gh run view --log` waits for the overall run to finish, the job-log endpoint
requires explicit escape-sequence acceptance when capturing terminal test logs,
and one HTTP 502 was retried as a read. Full logs remain private; no raw control
sequences or transcripts were copied into tracked documentation.

## Handoff and review

Private candidate artifacts, logs, receipts and three review manifests remain in
ignored `.work/rc8-qualification/`. No provider payloads, credentials, private keys
or sampling data enter this record. Exact source/artifact/report hashes and the
publication block are recorded in the final review. The run is waiting at the
separate publication approval; it was not granted. The rc.8 release is absent.

Stop rule reached: signed gates completed, independent unpaid cells completed,
and an evidence-backed product blocker identified and reviewed. Next: a new
reviewed candidate with a fixed frozen Linux launcher and fresh affected native
qualification. Do not retarget rc.8 or weaken isolation. Accountable release
approval remains Joshua's responsibility; this is the implementing agent's
technical review, not an independent approval.
