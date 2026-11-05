# rc.15 affected signed qualification review

Disposition: **affected signed qualification passes** for frozen source
`21fc2b02db5611d806626ad8c70698b3c7181577` (`0.1.0-rc.15`, storage epoch 2).
The owner subsequently accepted this evidence; immutable rc.15 is published as
release `435339429`. See [owner acceptance and public verification](RC15_PUBLICATION_WORK_NOTE.md).
This supplies the qualified replacement for rc.14's empty SBOM without rewriting
that published asset or closing unrelated stable-v1 gates.

## Frozen source and accountable authority

The owner explicitly requested review/merge, protected signing and affected
qualification. [PR #363](https://github.com/joshuamyers22/mos-eisley/pull/363)
merged normally after all 21 exact-head checks as
`83055ed6b5afe492670661ebe0cfe3b7b71f1307`; its tree equals the reviewed source.
The immutable annotated tag `v0.1.0-rc.15` has object
`ac6627da26ce8ab1488197fbd525fe7f7def93e7`, targeting that source in main's history.
Runtime dependency selection/export and epoch remain unchanged.

[Protected run 41948231550, attempt 1](https://github.com/joshuamyers22/mos-eisley/actions/runs/41948231550)
uses release workflow `350992511`. GitHub records `joshuamyers22` approving
`application-release`; the environment requires that owner and disallows admin
bypass. Solo-owner self-review remains allowed. The technical review is an
owner-directed operator review, not an independent human security attestation.

Protected preparation captured successful `make check audit`, build/container,
enrolled signing and complete software inventory generation. It passed 3,948
source tests in 3,985.111s (17 skips, 86% coverage), and 2,916 installed-wheel tests
in 2,652.445s (13 skips). Audit found no known vulnerability or adverse project
status across 54 packages. Signing custody was not read or changed by the operator.

## Actual signed evidence

All four signed jobs passed. Reconstruction authenticated the enrolled release
signature, exact source/version/epoch and four archive sizes/hashes, bootstrap
checksum set, root checksums, harness hashes and all expected report identities.
It admitted **58 reports and 76 prepared assets**. All 418 packaged runtime
Python source files match the frozen candidate in each of the four signed
archives; embedded code remains bound through the trusted protected build.

| Scope | Actual evidence |
|---|---|
| Signed install | macOS arm64/x86_64 and Linux arm64/x86_64; actual publisher-signed bootstrap install and signature/tamper refusal |
| Installed acceptance | Four matrices, each covering snapshot and SQLite: cold resume, committed recovery, passive reopen without replay, abrupt idle loss, terminal/diff stale-selection refusal, multiline/paste/resize and restored terminal modes |
| Actual predecessors | 44 journeys across eleven immutable releases; both-store preservation/recovery and uninstall, with exact enrolled metadata/archive/bootstrap bindings |
| Latest predecessor | Actual published rc.14 upgrade and same-epoch rollback on all four targets |
| Cross-epoch refusal | rc.1/2/3/5/7 on all four targets; rc.7 rollback refusal, readable legacy backup and rejection of candidate journals by legacy readers |
| Native diagnostics | Four six-case offline matrices: silent/output/exit waits, inherited pipe, valid-result wait and invalid-result wait; cleanup/replay refusal and unchanged static envelopes |
| Review validation corpus | Exact-candidate source checks preserve valid bound review and reject malformed/duplicate/conflicting/foreign-subject/extra-field artifacts; this is not the complete installed live coding path |
| Homebrew | Two actual generated-formula install/launch/test/uninstall journeys; public tap publication is separate |

The signed-install harness retains its disclosed synthetic older-metadata
same-code rollback case and inert Docker-client watchdog fixture. Those cases
are not substituted for actual historical upgrade evidence or real live coding
worker cleanup; the separate actual predecessor reports establish compatibility.
All reports record zero paid calls. No fresh provider grant or native subscription
invocation was created. rc.14's live receipts remain historical evidence.

## Actual software SBOM admission

The protected candidate SBOM is CycloneDX 1.6 with **6,485 components and 6,486
dependency records**. It covers the actual wheel/sdist, four applications and
four bootstraps, packaged metadata/license files, interpreter identities and file
hashes. The declared export selects 44 runtime packages per Linux target and 42
per macOS target; a separate standard `packaging` marker parser agrees on all
four sets. Every embedded bootstrap member agrees by size/hash with the pinned
PyInstaller reader: 164/164 Linux arm64/x86_64, 163 macOS arm64 and 166 macOS x86_64.
No PYZ/marshal content is deserialized or executed by this audit.

Independent offline official-schema validation and canonical recomputation pass.
Scratch copies with empty components, missing dependency records, boolean BOM
version, omitted CPython components or a stale file hash are rejected before API
access. All original prepared bytes remain unchanged. A read-only stdlib-only
publisher preflight against the actual tag/repository exits 0.

Unknown native-library versions remain hashed file identities, with no invented
version/CPE or license-clearance claim. Host OS and external native clients are
outside the release-payload inventory. The SBOM is not vulnerability clearance,
and no fresh live subscription latency or reliability claim follows from these
offline results.

## Preserved failures and resource disposition

The earlier local combined gate's test phases passed, but its Python 3.9 receipt
writer failed after completion; its uncaptured exit is not claimed. Successful
exact-head CI and this protected preparation provide captured successful gates.
The original SPDX-enumeration scanner finding, first assembly's prerelease spelling
refusal and local controller error remain disclosed in the candidate work note.

During this read-only audit, the strict publication parser correctly refused
historical epoch-1 metadata; the reviewer then used the existing retained-release
authenticator for historical inputs. No source, epoch guard, signature check or
retained metadata was relaxed. The first refusal remains private evidence.

Native/signing qualification finished at 04:46:10 UTC on 2026-11-05, inside the
six-hour execution window. The asynchronous operator wait outlasted the initial
observation window. A separate one-hour read-only closeout began at 13:26 UTC;
it launched no replacement qualification, native program, inference or signing.
See the [work note](RC15_QUALIFICATION_WORK_NOTE.md).

## Evidence bindings and remaining gate

| Evidence | SHA-256 |
|---|---|
| Enrolled `release.json` | `a7dc636d2dc1c6078694393dd27388b5fea53cbe9bb3d2bbe61d9a18e646915b` |
| Actual `release-sbom.cdx.json` | `a86e8daa7c86b3436a27b8b58b40c1cbe8792050bd69bd2704c4e39f3ea4a3b1` |
| Signed receipt reconstruction | `f8f8d0fbab6edf3162764d461182a8aef85153dd62a848ff180b4731f4d01671` |
| Actual signed SBOM review | `b8b437a68713351a8776a69495bd327d76e3edc11239f85e92bf55483bdf1ca6` |
| Packaged runtime source review | `b3aa61dd39b73df9d1da3a843049d47f7335638c366ced9d5c7a755a3bb8f707` |
| 76-asset inventory | `4e406d1176482f94516c6eee0adc36f738e54cbceac1bc2cda395653c07c1a52` |
| Protected preparation log | `584093e33e714d06bd2657d203ec1fa6b36e14730f75771d4bda280c324b624a` |
| Read-only preflight log | `c5055702f38b2c0d01a54e8d0f132bee5e6c6198148800757042230f03785a07` |
| Combined closeout record | `12a926d82c6d7993f7a57be762741d05aff33fb4a2c6a18c08ff91bcf7f37510` |

Private records are retained under the frozen candidate's
`.work/rc15-signed-qualification/`; no credentials, grants or raw provider content
are copied here. Ordinary engineering receipts convey no evaluation eligibility.

At qualification closeout, the workflow remained before `publish` at its owner
gate. The owner later explicitly authorized publication; the protected run
completed successfully and all 76 public assets, attestation, canonical SBOM and
fresh public installation were verified. See the [publication work note](RC15_PUBLICATION_WORK_NOTE.md).
The original qualification review did not renew a native scope, retarget a tag or
qualify stable v1.
