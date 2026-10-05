# G606-03 local candidate freeze and reproduction handoff

Status: **candidate package prepared; independent freeze and reproduction open**,
2026-09-28. This is the reproducible input package for the
[G606-03 validator](../tools/g6_06_reproduction_handoff.py), not a reviewer
decision or a target-host/build attestation. The worktree was dirty at capture;
HEAD `c6a427805a5eaf692de462c0f88ed42a4be5b8d0` alone does not reproduce
the candidate. The private package carries every bound source byte, including
uncommitted files.

## Candidate identity

The local package is
`private/g60603-candidate-20260928T0045Z` (operator-local and excluded from Git).
Its directory is mode `0700`, and each file is mode `0600`. It is ignored by
Git, so transfer it separately to an independently controlled location. The
`candidate-freeze.json` file has SHA-256
`915f11454d215914e3a517f06ae18de8a09e3b9c2ffe9ddec3ae40c9f764c47e`.
Verify that digest through the chosen custody channel before relying on any
other value in the package.

| Frozen component | SHA-256 or count |
|---|---|
| Bound source archive, `bound-sources.tar` | `1e551c259d42ca115294b5c47b5b40de70034a9fa692df694af9faf4a6d6690c` |
| Fresh baseline index, raw file | `fd82d3aa07f5d3ccdb8b6665a4ed253c430c434f22bcace514599d167310621e` |
| Fresh baseline index, canonical contract | `9e04c7a549f217dbb229989c6cb912bb78642d85cf0663f5e9ed780ec3acf24a` |
| Ordered source-set digest | `07eb35d3b637be34449cdcf1e175fe6c10bdea582868967a7437711f0b937bad` |
| Suite manifest digest | `7f9485a7ba306abfc5c46a3882942df15bd061bebe1d2776acdcfe8bbe75b861` |
| Full negative-case protocol digest | `f28c63b24e382a2099ec9575463f05eeb9dab7cef010a90441fe6cf2401250a0` |
| Replay command-template digest | `a4bf0cbc0d8911a41dea0e4d5c6b96ee53826081e79e85edb2ab0b1155789754` |
| `pyproject.toml` / `uv.lock` | `020c6ad97e084edeff2458f383947b767ccff59c943c4541c1198c823a71c1b9` / `c708faa66b01c5b8ee308ae21fe3382ab044e185b8496a2830aa572605dd9342` |
| Full runner source | `0eaafe4f5d6783a436c9b092e86918b800c477fede37e51fddce0dc83d597315` |
| Bound coverage | **306 files, 17 suites, 314 case IDs** |

The baseline was generated at `2026-09-28T00:47:01.773637+00:00` by
`uv run --frozen python -m tools.g6_06_full_offline` under CPython 3.12.14 on
macOS arm64. It reports `synthetic_pass`, stable source bytes and zero failures,
errors or skips. The ordered archive holds exactly the 306 files in that
index. Its tar entries have fixed metadata; none is a symlink or traverses
outside the extraction root. `README.md` is a separately hashed build-support
file (`08be2d09fc101b69ba6c3157e24d2654d2f5c9f8201389cd6a1f3becf444ed73`)
because `pyproject.toml` references it. It is outside the runner's bound source
set. The package contains no protected sampling registry, custodian mapping,
label store or outcome store.

`negative-case-protocol.json` lists every suite, test module, exact case ID,
case-ID digest and expected count. `replay-command.json` fixes the command
template with only the new private output path variable. The two `*-inputs.json`
files provide the pinned digests for the eventual anchor and replay record.
Their `status` fields and `null` reviewer, host, build and timing values make
them **invalid as validator inputs** until a separate custodian supplies and
freezes those claims. No value was inferred for a missing identity or build.

## Local extraction check

The same preparer extracted `bound-sources.tar` into a clean directory, added
the separately hashed `README.md`, installed the locked dependencies and ran
the fixed full-runner command. That result is kept as
`local-extraction-check-index.json` with raw SHA-256
`42f5424da2db4acd8969de9900a913a6e40cef18de970ebe48afb11d1219d732`.
It reports `synthetic_pass`: **314 tests in 17 suites**, with source entries
and suite results exactly equal to the baseline. The generation time and index
digest differ as expected. This check proves that the package can build and
run from its contents in this environment; it is not an independent reviewer
run or an exact target-host claim.

## Independent handoff procedure

1. Transfer the entire private directory to a distinct reviewer and an
   approved custodian. Verify the `candidate-freeze.json` SHA-256 above before
   trusting its contents. The bundled `verify-candidate.py` has SHA-256
   `53704b6091dccc0ac6120620c4e17ba5e600f3b6e5eef4fe4988fb43d58c83a8`.
   After verifying that script, run `python3.12 verify-candidate.py <package-dir>`;
   it checks file permissions, archive members, every source digest, all case
   IDs and counts, protocol/command digests and the local extraction index.
2. Inspect the complete source set and `uv.lock` under separate custody.
   Establish the actual broker build digest, baseline producer and host, and
   distinct expected reproducer and host. Copy `anchor-inputs.json` into the
   custodian's protected store, remove its `status` field, fill each `null`
   field, and freeze the valid `FrozenReproductionAnchor` **before** the replay.
   Its `frozen_at` must follow baseline generation and precede replay index
   generation; its expiry must cover the dated review. Never derive the anchor
   from replay output.
3. In a clean repository root, extract the verified source archive and place
   the verified support `README.md` beside `pyproject.toml`. Run
   `uv run --frozen python -m tools.g6_06_full_offline
   <new-private-replay-index.json>`. Keep the exact command template and
   negative-case protocol digests from the package. Record the actual build,
   host and reproducer identifiers without substituting this preparer's
   local extraction result.
4. Fill `reproduction-record-inputs.json` from that fresh index and observed
   replay metadata, remove its `status` field, then run
   `uv run --frozen python -m tools.g6_06_reproduction_handoff
   <frozen-anchor.json> <baseline-index.json> <replay-index.json>
   <reproduction-record.json> <new-private-assessment.json>`.
   Compare every mismatch category and retain an explicit dated disposition.
   `metadata_match` is a structural result with all release and assessment
   authority fields false. A separate reviewer must authenticate source,
   host/build and reviewer custody before accepting G606-03.

Sampling receipts are metadata only and provide no holdout assignment or
authority. This package is a source and test snapshot, not a sampling artifact.
Its indices and manifests contain only paths, case IDs, counts and digests;
the source archive contains the exact bound code and synthetic tests.
