# Pure namespace-record codec verification

Status: codec implementation and full gate complete; GitHub CI and accountable admission pending. Owner: Josh Myers. Date: 2026-10-04.
Branch: `feat/namespace-record-codec`. Base: contract commit `3c994c0`.

Objective: implement only the immutable version-1 namespace metadata value and
bounded canonical encoder/decoder specified by the
[contract](NAMESPACE_STORAGE_CONTRACT.md). Freeze synthetic POSIX and full-SID
Windows golden bytes and digests. No storage operation, enrollment context, key
creation/custody, consumer adoption, writer or public Windows selector activation.

Invariants: exactly five wire members; explicit version and fingerprint; no legacy
fallback; at most 4,096 bytes before parsing and after encoding; duplicate and
noncanonical inputs refuse. A decoded record grants no enrollment authority.
Existing identity wire formats and legacy hashes remain unchanged. Imports and
round trips perform no native, filesystem, randomness, clock or credential action.

Guidance: [Python engineering](PYTHON_ENGINEERING_GUIDE.md),
[verification guide](AGENTIC_VERIFICATION_GUIDE.md), work-note and verification-loop
templates; [identity threat model](PLATFORM_IDENTITY_THREAT_MODEL.md) and
[ADR-0016](adr/0016-namespace-record-storage-admission.md). Risk: material parser and
metadata trust boundary; accountable review is required for admission beyond this
additive codec. Synthetic fixtures only; no live private stores or sampling data.

Rubric: N-01 exact golden bytes/digests and version/tag/width validation; N-02
preparse bound, duplicates/hostile encoding refusal and inert source/wheel import;
N-03 decoded/copied metadata cannot supply an enrollment context (storage and
protected-anchor checks remain future work); N-14 existing identity and legacy
fixtures unchanged. Required evidence: focused source regressions, lint/format and
typing, clean dependency-free installed-wheel tests and diff readback. Full
`make check` is required before publication. Publication was subsequently authorized
after the implementation commits.
Ceiling: three correction passes and two hours active implementation. Stop after
the focused and artifact evidence passes; no repeated full suite without a new
failure or code change. Native storage/enrollment qualification remains pending.

## Evidence and handoff

Implemented `NamespaceRecord`, `encode_namespace_record` and
`decode_namespace_record` in the existing inert
[wire module](../src/mos_eisley/platform/identity_wire.py). Fixed kind/version are
immutable constructor constants but remain required wire members. The exact
namespace, tagged principal and public-key fingerprint are validated at creation;
decoding uses the shared bounded canonical parser. No new dependency, storage or
selector path exists.

Nine [namespace tests](../tests/test_platform_identity_wire.py) freeze literal
POSIX/Windows golden bytes and independent SHA-256 digests, distinct from the
synthetic public-key fingerprint. They cover all SID widths, malformed fields and
versions, legacy/cross-codec refusal, duplicate/hostile encodings, exact 4 KiB and
oversized inputs/outputs, wrong input types, redacted immutable values and clean
subprocess imports/round trips with OS/native/filesystem/randomness/clock traps.
The existing Windows wheel selector now explicitly includes this test class in
[installed platform smoke](../tools/smoke_platform_files.py); source Windows CI and
full package discovery already cover the enclosing wire test module.

Verification on macOS, Python 3.12.14:

- Focused wire/identity/legacy tests and SQLite permission/owner/cursor boundaries:
  **51 tests passed in 1.057 seconds**, no skips.
- Repository Ruff lint and format checks passed; Pyright reports zero errors or
  warnings. Initial formatting and invalid-fixture typing findings were corrected.
- Frozen Hatchling sdist/wheel build passed after pinned build dependencies were
  fetched outside the network-restricted sandbox. Wheel codec bytes match the
  current source file.
- Dependency-free fresh-wheel platform smoke: two legacy-byte tests passed; 101
  platform tests completed in 0.528 seconds, **93 passed and eight native Windows
  tests skipped**. All nine new namespace tests passed from the wheel. Skips grant
  no Windows admission.
- Diff/readback verifies the additive implementation preserves existing wire
  functions and platform selectors; `git diff --check` passed. Documentation links
  resolve. Plan, roadmap, migration design, ADR and memory reflect this slice.

N-01/02 and metadata-only N-03/N-14 have focused executable evidence. Protected
anchor, copied-store/root/key proof, native storage/enrollment tests and accountable
review remain pending. The contract documents were committed separately as
`3c994c0`; the implementation is `cc3ee8b`.

## Full gate and publication preparation

The full combined `make check` completed with exit status zero on 2026-10-04 at
implementation revision `cc3ee8b`. Source: **2,795 tests in 2,431.534 seconds**, OK
with **12 skips**; aggregate coverage **86%**. Fresh installed package: **2,040
tests in 1,594.556 seconds**, OK with **eight native Windows skips**. Ruff lint,
format, Pyright, locked export verification and Hatchling wheel/sdist build passed.
The interrupted sandbox attempt is excluded: a localhost-bind probe returned
`PermissionError`, so only this task's gate processes were stopped and the full
gate restarted with the required access. The completed run is the publication
check; no code changed after it. Disposable output stays outside Git at
`/private/tmp/mos-namespace-record-make-check-native-access.log`.

Current `origin/main` (`b3546f9`) is already an ancestor. Prerequisite PR #270
(identity wire codecs), #268 (file identity) and #266 (principal identity) remain
open at publication preparation. This branch retains that dependency chain and
targets `main`; its comparison will include prerequisite commits until they merge.
The user authorized push and PR creation after the full gate. Actual Ubuntu and
native Windows source/wheel CI and accountable review remain required; local skips
do not admit Windows selectors, storage or enrollment.

Next smallest slice: read-only POSIX admission of an already-open root, including
actual descriptor ACL/mount eligibility, owned non-inheritable lease lifetime and
failure cleanup. Keep child reads separate until root admission qualifies; writers,
consumer adoption and public Windows selectors remain gated.
