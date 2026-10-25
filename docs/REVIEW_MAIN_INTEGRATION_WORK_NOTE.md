# Review stack integration with current main

- Status: closed; protected integration merged, frozen release qualified separately
- Owner: Joshua Myers; implementation/technical verification by Codex
- Started: 2026-10-24 UTC; review by: rc.8 qualification disposition
- Main input: `6fe0769` (merged dependency integration #332)
- Review input: `dac047c`, followed by fixture correction `eadb415` (#333)
- Worktree/branch: `integrate/review-platform-main`

## Objective and source distinction

Joshua requested integrating the review/platform work and qualifying a preview.
He subsequently selected #333's tested dependency set for that preview. Freeze
the rc.8 release candidate at `eadb415d31afd89b142e3229a8ccca72aca835ee`.
Its application/lock bytes equal the earlier tested `dac047c`; only test fixtures
and documentation changed. Keep its separate exact qualification runs.

#332 merged concurrently and made #333 conflict with main. Integrate the review
commit ancestry into current main in this separate worktree, preserving main's
already merged provider/HTTP dependency versions, privacy guard and action pins.
Those dependencies do not enter the frozen rc.8 artifact. A protected merge of
this integration makes the frozen candidate reachable from main; its own immutable
tag, source/version, signing and artifact gates still apply. No main rollback or
dependency downgrade is authorized or performed.

## Guidance, invariants and bounded verification

Use repository AGENTS/CONTRIBUTING, Python engineering, bounded verification,
adversarial review, threat-model and work-note guidance. Retrieved README,
brief/memory, #332's SDK privacy record, #333's integration/credential/recovery
records and actual dependency/workflow diffs. Material security-sensitive
integration; agent technical review supplies no independent release approval.

Preserve both commit histories, owner state, immutable releases, default-inactive
credential attachment, current source admission, blind role contexts, spending,
cancellation and recovery. No provider inference, real credentials, sampling
stores, studies or publication. The preview's user-selected dependency lock stays
frozen in its original worktree.

One focused cross-dependency pass, then one coherent full `make check audit`
before PR publication; at most two evidence-backed corrections per new failure.
Allow four hours per full native gate with process-bound sleep prevention and
zero model spend. Stop on failed guards, stale/mismatched inputs or missing
accountable release disposition. Failed/interrupted work is never a pass.

## Merge resolution and acceptance

The only textual conflict is the legacy-upgrade workflow: retain #333's reviewed
metadata custody and epoch-1 harness selection, with main's setup-uv action pin.
Use that same main pin in the newly added native-review workflow. The merged
manifest/lock preserve main's dependencies; the project version alone becomes
rc.8. Retain the main Anthropic SDK-2 tracing/privacy control.

Blocking evidence: credential sockets/logging under current HTTP dependencies;
scoped/managed-worktree review and retained source freshness; current real-SDK
privacy regression; storage epoch/publication guards; source/wheel quality,
coverage, export/build/audit and exact protected integration CI. The frozen
preview retains separately recorded native/signed qualification.

## Verification record

All 129 focused cross-dependency checks passed in 73.084s, including real
credential sockets/logging and the real-SDK ambient-tracing privacy regression.
Repository Ruff/format, strict Pyright and frozen runtime export verification
passed. The combined awake `make -j1 check audit` exited 0: 3,876 source tests
in 2,835.084s (17 platform skips), 86% coverage, 2,863 fresh installed-wheel
tests in 1,941.602s (13 platform skips), clean export/build, and audit reporting
no known vulnerabilities/adverse project statuses in 54 packages.

This local gate uses current-main dependencies and does not substitute for the
owner's selected older-dependency preview. Final protected CI is recorded below.

The follow-up merge retains `eadb415` ancestry and its two test-only changes:
explicit unsafe-fixture permissions under umask 077 and failure assertion context.
The frozen preview lock/application bytes remain unchanged. Current-main affected
subscription suites pass all 43 cases under umask 077; current-head static checks
pass. The earlier WSL2 failure and unknown early-return cause remain recorded
in the preview work note; corrected native CI passed as recorded below.

## Protected integration closeout, 2026-10-25

[PR #334](https://github.com/joshuamyers22/mos-eisley/pull/334) merged at
`b5d2c766bafca7ce17eac5c9e7b92fb23eb297bb` after all 22 final-head checks
passed at `f498b98`. Tested merge `a5dab66` has the identical tree
`57e6ff2aaffbb85d78e7e80d93fb1ed2d4a75b45`. Both original histories are
retained; #333 closed through this integration. Owner worktrees remain untouched.

[Current-main native run 40153431249](https://github.com/joshuamyers22/mos-eisley/actions/runs/40153431249)
passed Linux and actual Windows-hosted WSL2: 3,876 source / 2,863 installed-wheel
tests (17/13 platform skips), plus 116 source and 116 installed focused cases per
platform with zero failures/errors/skips. Both 414-file wheel hashes agree:
`d401f74ec226699769b6539946cbf52ea786145b2a4171369999f34ac6c66009`.
Host/candidate/run/bundle identities and actual distro version 2 were checked.

The dependency-frozen preview is separately tagged `v0.1.0-rc.8` at `eadb415`,
verified reachable from protected main. Its exact native gate and tagged assets
are recorded in the [preview work note](RC8_REVIEW_PREVIEW_WORK_NOTE.md).
The [release run](https://github.com/joshuamyers22/mos-eisley/actions/runs/40217716964)
is the live signed-artifact qualification record. Joshua approved signing
preparation only, including the epoch-2 rollback limit; publication requires a
separate approval. Main integration closes here without granting broader WSL2,
provider activation, study, stable launch or publication authority.
