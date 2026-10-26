# rc.9 Linux launcher repair: prepublication review

**Technical qualification passes; publication remains withheld for owner review.**
RC8-Q01 is closed in this new candidate. Both Linux architectures now execute
confined Git and pass actual signed terminal/diff acceptance on snapshot and
SQLite. All four macOS/Linux targets pass signed installation, the installed
matrix and the actual-predecessor journeys. rc.8 remains blocked on its original
artifacts; none of its failed evidence is relabeled or replaced.

- Review date: 2026-10-26 UTC.
- Accountable release owner: Joshua Myers.
- Technical implementation/review: Codex, also the qualification-harness author;
  this is not independent security review or accountable publication approval.
- Frozen source: `f94842a44b9fc5dcf42a7f5880a6683e4fdc0b23`.
- Annotated tag: `v0.1.0-rc.9`; tag object `4ecad837a378c78a3242f82adb45523f327e3023`.
- Version/storage epoch: `0.1.0-rc.9` / `2`.
- Main integration: [PR #336](https://github.com/joshuamyers22/mos-eisley/pull/336),
  head `dfe6e2e66e3f4c4659c032d9edf5534e31249522`, merged at
  `a73edc655c78be15e54aa8a7649cb7479a1f8566` after all 13 checks passed.
- Protected release: [40246538826](https://github.com/joshuamyers22/mos-eisley/actions/runs/40246538826).
- Signed publication candidate artifact: `12624107098`; no release publication occurred.

## Repair and retained boundaries

[The frozen entry](../src/mos_eisley/_frozen_entry.py) recognizes one fixed
Linux-only helper mode before CLI/provider composition. The broker's frozen
command reaches that compiled-in helper instead of passing Python interpreter
flags to the ordinary CLI. Source/wheel execution retains isolated Python module
loading. The existing seccomp ABI checks, process/network restrictions, absolute
executable checks, bounded ownership/deadlines and refusal on confinement failure
remain. No external interpreter substitutes for the native product.

The native regression requires actual Git output, child-process/network denial
and relative-target refusal on both Linux targets. Its host Python is only a
negative syscall probe. Both development and actual enrolled-key installation
receipts pass these checks. Both macOS entries refuse the private Linux mode;
their existing Seatbelt-backed terminal/diff journey also passes.

The candidate retains rc.8's dependency versions; its lock changes only the project
version. The separate integration preserves main's newer SDK/HTTP migration,
privacy guard and action pins, with the frozen candidate in main's ancestry.
Original source `eadb415`, tag `v0.1.0-rc.8`, signed assets and failed receipts
remain preserved. See [RC8-Q01's original review](https://github.com/joshuamyers22/mos-eisley/blob/017f00743d15435e02e030ecfab9992314a65b1b/docs/RC8_PREPUBLICATION_REVIEW.md#blocking-finding).

The signed matrix is now a required release step bound to the explicit source
SHA and tag version. A failed job blocks publication. Its report upload uses
`always()` so a failed matrix's written receipt is retained; the workflow
contract test covers that retention without allowing errors to pass.

## Protected build and signature review

Exact-source preparation passed 3,880 source tests in 4,018.651s (17 platform
skips), 86% coverage, and 2,856 clean installed-wheel tests in 2,652.862s (13 skips).
Frozen export/build, locked audit of 54 packages, container checks and SBOM
generation passed. Platform skips are not passing native evidence.

Local review verified the enrolled Ed25519 metadata signature, exact
source/version/epoch, root `SHA256SUMS`, all four native archive sizes/hashes and
all four bootstrap checksums. The Git tag is annotated, not GPG-signed; application
authenticity comes from the enrolled metadata signature and protected custody.

Signed metadata SHA256:
`692b694d2683809f9a8fccd4499f682247a3c17702c2891a20f334750fe5dc23`.

| Target | Signed archive SHA256 |
|---|---|
| linux-aarch64 | `ec52c65cd9a6e1ae048188eb19aa6299d1fc55fe07ad1c50ce2fba1cd6674e9e` |
| linux-x86_64 | `fc8e6a822b2d702ca6bd5fa91179f0e6fbb29b2f02579f6a9edc26e46bc72c2a` |
| macos-aarch64 | `107ab2e42367e27b0227039e3354b034128883ce99ca0f0d2380c5b590a7ec4a` |
| macos-x86_64 | `4f4dd2e4fed910cc35f76f3b073b95a66c20920e7be706b0207c15bb34f298a0` |

Bootstrap manifest SHA256:
`db6ce55631f45ebbd3474b270512c7d083c685b34d14fdf7509e40fb5b3850f1`.

## Actual installed and predecessor evidence

All four `qualify-signed` jobs passed. Review validated all 30 JSON receipts:
four actual enrolled-key signed installations, four installed matrices, twenty
actual-predecessor upgrades (rc.1/rc.2/rc.3/rc.5/rc.7 on each target), and two
actual generated Homebrew formula installation/test/uninstall journeys. Receipt
source, metadata/archive/bootstrap bytes and zero paid calls match the candidate.
Generated-formula hashes match the prepared formula; only the fixture archive URL
was substituted. The public tap was not updated and Apple cask/notarization was
not qualified.

| Native target | Signed install | Snapshot + SQLite terminal/diff, resume and recovery | Five actual predecessors |
|---|---|---|---|
| Linux aarch64 | Pass | Pass | Pass |
| Linux x86_64 | Pass | Pass | Pass |
| macOS aarch64 | Pass | Pass | Pass |
| macOS x86_64 | Pass | Pass | Pass |

For all eight target/backend combinations, the installed native runtime passes
positional/stdin NDJSON framing, committed operation/cursor evidence, exact
consumed-attempt/journal preservation through passive reopen, one admitted
follow-up, abrupt idle-terminal process loss with unchanged committed history,
and empty/malformed UTF-8/oversized-input refusal before session creation.
The real PTY passes frozen diff attachment, stale-source send refusal with draft
retention, excerpt removal, Unicode/multiline bracketed paste, resize/draft
preservation, normal terminal-mode restoration and contextual cold resume.
Both Linux launcher probes exit 0 with actual Git version output.

Installed harness SHA256:
`7fe9337cdd4a18ff92843ee729cb05e46db10eb04158af3e86608c1d59d5840b`.
All four matrix receipts match that harness and the signed candidate identities.
The driver uses host standard-library orchestration and the installed native
bootstrap/executable; it does not import source-tree product code.

All five published predecessors are epoch 1. All twenty journeys prove explicit
cross-epoch rollback refusal without pointer/state mutation, candidate
continuation, legacy-backup readability, old-reader rejection of new state,
pre/post-activation recovery, tamper refusal and both uninstalls on both stores.
In particular, rc.7 passes on all four targets. Their published source, metadata,
archive and bootstrap identities also match retained previously verified evidence.
`candidate_written_session_rollback` correctly remains **false** for these
cross-epoch pairs. Keep an epoch-2 reader and pre-upgrade copies under
[ADR 0019](adr/0019-recovery-release-storage-epoch.md).

The abrupt-loss probe kills an owned idle terminal after a committed result.
It does not claim installed injection of an in-flight paid call or uncertain
write acknowledgement. Those mechanisms retain source/wheel test evidence.
This is the unpaid recorded acceptance scope, not full v1, live effectiveness,
general Windows/WSL2 or operational acceptance. No provider call or study ran.

## Inventory, resource bounds and disposition

The publication inventory validator admits 47 unique assets, including all 30
qualification reports. It checks completeness and bytes; it grants no publication
authority. Private review manifests retain the detailed receipt/asset identities:

| Private review manifest | SHA256 |
|---|---|
| `receipt-review.json` | `69fca6e148b6a663078841f519820f8f1d6d3904499f9a2c63fbe282e88f7495` |
| `predecessor-identity-review.json` | `5bc18384e3785046b32b40b8a13bdeef1d0747e1e86e16c2fe5435c9fa1c9f08` |
| `inventory-review.json` | `d827d58ceb1039f296fdd8ee02d58f8acdc4a9f8ef328bfad8019867a5bba3d7` |

Protected preparation took 116m45s; the longest signed job took 37m45s, within the
150/75-minute job ceilings and four-hour per-gate budget. Status watchers lost a
connection and later hit a TLS timeout. Read-only monitoring was reconnected;
remote tests were not rerun. Final fresh job/artifact records and all receipt
assertions were reviewed after reconnecting.

Approval history contains one preparation approval only. The protected run is
waiting at `publish`; publication approval remains withheld. RC8-Q01 is resolved
for rc.9, with no remaining technical failure in the requested qualification.
The next decision is the owner's review of this exact evidence and separate
publication disposition. This record does not authorize publication.
