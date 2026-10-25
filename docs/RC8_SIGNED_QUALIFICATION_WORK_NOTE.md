# rc.8 signed candidate and installed qualification

- Status: active
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

Pending signed artifact preparation and native evidence. Development publisher
fixtures do not count as enrolled-key qualification. Supplemental source/helper
development runs are recorded separately from final installed artifact evidence.

## Handoff and review

Private disposable artifacts remain in ignored `.work/`. No provider payloads,
credentials, private keys or sampling data enter this record. Fill exact hashes,
job results, observed limitations and final review before publication disposition.
