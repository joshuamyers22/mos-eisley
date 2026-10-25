# rc.8 signed candidate prepublication review

**Verdict: block publication of the requested macOS/Linux preview.** Build,
signing, signed installation and actual-predecessor qualification passed. The
installed acceptance matrix exposed a Linux frozen-launcher defect that prevents
the required diff panel from acquiring its Git isolation boundary. Both macOS
targets pass the installed terminal/diff checks; both Linux targets fail that
boundary on snapshot and SQLite. No release was published and no provider call
was made by this qualification.

- Review date: 2026-10-25 UTC.
- Accountable release owner: Joshua Myers.
- Technical review: Codex, also the supplemental harness author; not independent
  security review or accountable release approval.
- Exact source: `eadb415d31afd89b142e3229a8ccca72aca835ee`.
- Tag: `v0.1.0-rc.8`, preserved in main through merge `b5d2c76`.
- Version/storage epoch: `0.1.0-rc.8` / `2`.
- Protected release run: [40217716964](https://github.com/joshuamyers22/mos-eisley/actions/runs/40217716964).
- Final installed acceptance: [40230486519](https://github.com/joshuamyers22/mos-eisley/actions/runs/40230486519),
  harness commit `2d3c3cd7809680bd604dab2011f00f3ad14df30b`.
- Earlier installed run [40229624329](https://github.com/joshuamyers22/mos-eisley/actions/runs/40229624329)
  remains failed evidence; it passed both macOS targets and stopped Linux at its
  first diff check. The follow-up retained the failure and completed independent
  SQLite checks and a direct launcher diagnostic.

## Build and signing evidence

Protected preparation passed the frozen candidate's full gate: 3,875 source tests
run with 17 platform skips, 86% coverage, 2,851 installed-wheel tests run with
13 platform skips, clean locked audit of 54 packages, container checks and SBOM
generation. Skips are not counted as passing platform evidence.

The dedicated protected preparation produced `application-publication` artifact
`12611865136`. Local review verified its enrolled Ed25519 metadata signature,
exact source/version/epoch, root `SHA256SUMS`, all four archive size/hash values
and the four bootstrap checksums. The Git tag is not GPG-signed; this review's
application-authenticity claim is the enrolled Ed25519 metadata and protected
artifact custody, not a Git tag signature.

Signed metadata SHA256:
`867626d69b4caca4e6882f0904d242898f001dbfd63cfbc9123c99332aa6b9f7`.

| Target | Signed native archive SHA256 |
|---|---|
| Linux aarch64 | `6b5a9aad22462fe5b379aba90476b62c699241a2a0c8f496391ef5d71808f3ce` |
| Linux x86_64 | `0ba1a6b9528f1939c18aa73c37057e1b9a3f58b8bf594fd7a9d331a7b6242a62` |
| macOS aarch64 | `9471d1164167c262bbf5f463a6ac240a486481a2f9244c0ac822510d807191c0` |
| macOS x86_64 | `a00513d3e784cbb9aeb1ca9997369afd024c9929dc8a82018763b4818b4fb798` |

## Signed installation and upgrade results

All four `qualify-signed` jobs passed. Review cross-checked all 26 JSON receipts
against the exact signed metadata/archive identities, source and zero paid calls:

- Four actual enrolled-key native installation receipts, including credential-free
  setup, archive/runtime tamper refusal, installed exec/recovery on both stores,
  cold resume, interrupted activation recovery and state preservation.
- Twenty untouched actual-predecessor journeys: rc.1, rc.2, rc.3, rc.5 and rc.7
  on each of the four native targets. Each receipt verifies source, metadata,
  archive and bootstrap identity and both session stores.
- Two actual generated-formula installation/launch/test/uninstall receipts on
  macOS. They replace only the selected archive URL for the fixture; neither a
  public rc.8 tap update nor Apple notarization/cask qualification is claimed.

Every published predecessor is epoch 1. Every actual upgrade receipt proves
forward installation to epoch 2, candidate continuation, cross-epoch rollback
refusal without state/pointer mutation, pre/post-activation recovery, archive/
runtime tamper refusal, separate legacy-backup readability, rejection of new
candidate state by the old reader and both uninstalls. In particular, all four
rc.7 pairs pass those checks.

`candidate_written_session_rollback` is correctly **false** for these actual
cross-epoch pairs. The synthetic same-code rollback exercise proves transaction
mechanics only; it does not establish backwards readability of new journal state.
Preserve an epoch-2 reader and pre-upgrade copies under [ADR 0019](adr/0019-recovery-release-storage-epoch.md).

## Installed unpaid acceptance results

The supplemental workflow downloaded the same protected signed artifact, used
the unpatched enrolled-key native bootstrap and launched the installed native
executable. It did not import source-tree product code or substitute an external
Python for the product. Its diagnostic driver uses only the host standard library.

| Target | Both-store exec and stdin | Passive reopen and committed-history recovery | Terminal, diff and stale-source refusal | Result |
|---|---|---|---|---|
| macOS aarch64 | Pass | Pass | Pass | Pass |
| macOS x86_64 | Pass | Pass | Pass | Pass |
| Linux aarch64 | Pass | Pass | Blocked by Git isolation failure on both stores | Fail |
| Linux x86_64 | Pass | Pass | Blocked by Git isolation failure on both stores | Fail |

For all eight target/backend combinations, actual signed runtime checks pass
positional/stdin NDJSON framing, committed operation/cursor evidence, exact
consumed-attempt preservation through passive reopen, one new admitted follow-up,
abrupt idle-terminal process loss with unchanged committed history, and empty/
malformed UTF-8/oversized-input refusal before session creation.

On both macOS targets and both stores, the real PTY additionally passes frozen
diff attachment, stale-source send refusal with retained draft, removal, Unicode/
multiline bracketed paste, resize/draft preservation, normal exit/terminal-mode
restoration and contextual cold resume. Linux stops at acquiring the diff; its
later dependent terminal assertions are unproven, not evidence that Unicode or
terminal restoration independently malfunctions.

The process-loss case kills an owned **idle** terminal after a committed result.
It does not claim native injection of in-flight paid-call/write acknowledgement
loss. Those mechanism cases remain the exact source/wheel recovery tests; no
live credentialed experiment or study occurred.

Final supplemental harness SHA256:
`680a605cb5fc75f2acb79099463a11346122bb33646b4498e7153696c3d2cea4`.
All four final receipts match that harness hash and the signed source, metadata
and corresponding native archive hashes. Failed receipts retain a failed overall
status and nonzero job exit rather than converting the failure into a skip/pass.

## Blocking finding

**RC8-Q01 — Linux frozen runtime cannot enter its isolated Git launcher. High.**

Both installed Linux binaries display `OS Git isolation is unavailable` when
`/diff` tries to read a controlled local repository. The supplemental direct
launcher probe exits 2 on both architectures instead of producing a Git version.
The same signed artifacts pass ordinary installed chat and both-store recovery,
so those successes do not qualify the Git-backed terminal journey.

The frozen-source trace explains the packaging boundary:

- [conversation_git_isolation.py](https://github.com/joshuamyers22/mos-eisley/blob/eadb415d31afd89b142e3229a8ccca72aca835ee/src/mos_eisley/conversation_git_isolation.py)
  invokes `sys.executable -I -m mos_eisley._git_read_linux` on Linux.
- [app_entry.py](https://github.com/joshuamyers22/mos-eisley/blob/eadb415d31afd89b142e3229a8ccca72aca835ee/tools/app_entry.py)
  routes the frozen executable into the ordinary Mos CLI. It is not a Python
  interpreter entry point for that module invocation.
- [conversation_git.py](https://github.com/joshuamyers22/mos-eisley/blob/eadb415d31afd89b142e3229a8ccca72aca835ee/src/mos_eisley/conversation_git.py)
  refuses when its version probe fails, preserving the required isolation guard.

No missing-package installation, weaker sandbox, substituted external interpreter
or guard bypass was used to make Linux pass. Source/wheel Linux results do not
replace this failed frozen-binary evidence. The report's diagnostic flag for
finding the literal `-I` text in stderr is false and is not used as an assertion
about the exact parser message; exit 2 and the runtime/source trace are the evidence.

The smallest next engineering slice is a reviewed fixed-module frozen launcher
route, preserving the existing seccomp/process/network restrictions, absolute
trusted Git binding, resource limits and failure refusal. Add native frozen-binary
positive and negative regressions, select a new reviewed candidate/version, and
repeat affected exact-source signing and installed qualification. Preserve
`eadb415`, its immutable tag, its signed artifacts and all failed receipts.
Owner: Joshua Myers; blocking review point: before publication. This task did not
change the frozen product to repair that defect.

## Evidence inventory and disposition

The original release inventory validator admits 43 unique candidate assets after
assembling the signed reports locally. This is a completeness check, not a
publication decision. Four supplemental installed reports are retained separately
from that original publication inventory.

| Local private review manifest | SHA256 |
|---|---|
| Signed installation and predecessor receipts | `5b19c1d175cc8b002722071806daba1f0dc65b7a826e546088f8ff335f8a1e65` |
| Final installed receipts and blocking verdict | `f1650e8c32271420648036f40d0c7498b29cd3126688bcb282561621f026de24` |
| Original publication asset inventory | `a7a4b18f59b94940a0223a8bfbaca8debf37dd6b1e16e60770688959273c5991` |

The protected release run is waiting at `publish`. Review history contains only
the preparation approval; this task issued no publication approval. The rc.8
release endpoint returns 404. Native/signed build success therefore does not mean
rc.8 is available or approved for production.

The requested build, signing, execution and prepublication review are complete
with a blocking finding. Full v1, general WSL2/native Windows, broader repository
execution, live effectiveness, Apple cask/notarization and operational acceptance
retain their existing gates. Do not publish the requested four-target preview
until RC8-Q01 has a verified disposition. See the
[qualification work note](RC8_SIGNED_QUALIFICATION_WORK_NOTE.md) for scope, failed
attempts, resource bounds and verification records.
