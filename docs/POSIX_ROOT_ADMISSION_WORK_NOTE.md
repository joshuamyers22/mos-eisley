# Read-only POSIX root-admission candidate

Status: candidate implementation and full publication gate complete; native CI and accountable admission pending. Owner: Josh Myers. Date: 2026-10-04.
Branch: `feat/posix-root-admission`; baseline `74acdd8`, dependent on PR #272.

Objective: implement direct candidate admission of an already-open POSIX directory
under the [namespace/storage contract](NAMESPACE_STORAGE_CONTRACT.md), with actual
bounded ACL/mount checks and an owned non-inheritable lease. No path selection,
child reads, namespace creation/enrollment, store adoption, writer or Windows
selector changes. Public storage selection remains closed until target evidence
and accountable review admit it.

Guidance: Python engineering and agentic verification guides, adversarial review
playbook, work-note/verification-loop/threat-model templates and ADR-0016.
Risk: material native-query and owned-reference trust boundary. Invariants: caller
keeps borrowed descriptor live through duplication; caller descriptor/offset/flags
are untouched; fresh real/effective/expected owner equality; exact private mode;
actual ACL and filesystem observations; no on-read effects or authority promotion.
Rubric: N-04 principal refusal; N-05 lifecycle/non-inheritance/cleanup; N-06 real
ACL/protection; relevant N-07 special/unqualified filesystem refusal; N-09 bounded
queries; N-14 legacy preservation; N-15 real-source/wheel target evidence.
Ceiling: three corrective passes, two hours active work. Focused faults/native
fixtures, lint/type and clean wheel checks decide completion; full `make check`
required before publication. Linux native evidence and accountable admission are
pending when unavailable on this Mac. No private live stores or sampling artifacts.

## Initial candidate policy and trust boundary

Darwin LP64 little-endian arm64/x86_64: descriptor `fstatfs` local APFS with ownership
honored and no removable flag; fixed-buffer `fgetattrlist` extended-security query,
require descriptor extended-security support and refuse any ACL entry or
unrecognized security flags/format. Permit the known APFS data-volume extended
mount flag only; reject unknown extended mount flags. Linux LP64 little-endian glibc
x86_64/aarch64: descriptor `fstatfs`, ext2/3/4 shared magic only; bounded `fgetxattr`
access/default ACL inspection, absent or exact base access ACL with no default ACL.
Do not claim the shared Linux magic distinguishes ext4 or proves physical backing,
mount ancestry, durability or host enrollment. Policy identifies an observed local
filesystem class; separately selected anchor scope remains the caller's obligation.
Unknown architectures/libcs/filesystems/protection refuse. Neither native query
uses a pathname or an unbounded allocating ACL API.

Assets: private root metadata, principal/root/protection integrity, borrowed and
owned reference lifetimes. Actors: untrusted retained data and concurrent same-owner
changes; kernel/admin/fully trusted same-owner process compromise excluded. Abuse
controls: mode-only ACL bypass requires real ACL inspection; copied IDs grant no
lease; descriptor/path replacement cannot redirect held root; principal/protection
changes refuse; query buffers cap at 64 KiB; uncertain close blocks acquisitions
without retrying a potentially reused FD. No new accepted privacy exception.

## Evidence and handoff

Implemented the direct
[POSIX candidate](../src/mos_eisley/platform/posix_storage.py),
[bounded native queries](../src/mos_eisley/platform/posix_storage_native.py) and
[inert gated boundary](../src/mos_eisley/platform/storage.py). Acquisition observes
the borrowed root, duplicates atomically with `F_DUPFD_CLOEXEC`, and checks duplicate
and borrowed observations again. Each observation brackets queries with fresh
principal, access-flag and fstat checks; subsequent `inspect()` compares two fresh
observations with the original identity/protection/mount/ctime binding.

The lease exposes advisory observations, not a descriptor, enrollment context or
write grant. It is context-managed, nonserializable/noncopyable and idempotently
closed. Failed context entry releases its owned reference. Close failure retains
bounded uncertain ownership, never retries that descriptor, and disables further
acquisition until process reset. At most 64 owned/uncertain leases exist; capacity
and uncertain-release errors are distinct. Callers must explicitly close leases;
there is no garbage-collection or process-shutdown cleanup promise.

Native corrections backed by fixtures: arm64 Darwin uses `fstatfs` while x86_64
uses the inode64 symbol; the APFS data-volume flag is recognized explicitly.
Absent Darwin ACL data has an exact empty attribute-reference form, accepted only
with positive descriptor extended-security support. A frozen empty filesec also
requires known magic, zero UUIDs/flags and no entries. The kernel source documents
these layouts; no allocating ACL API or pathname fallback is used. This Mac strips
set-UID on directories, so actual mode refusal fixtures use preserved special bits
rather than pretending the requested bit survived.

Primary API/ABI references:
[Apple attribute and relative-reference layouts](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/attr.h),
[Apple filesec and ACL layout](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/kauth.h),
[Darwin statfs/mount flags](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/mount.h),
[extended-security pathconf constant](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/unistd.h),
[kernel empty-ACL packing](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/vfs/vfs_attrlist.c),
[glibc statfs layout](https://github.com/bminor/glibc/blob/master/sysdeps/unix/sysv/linux/bits/statfs.h),
[Linux ACL xattr layout](https://github.com/torvalds/linux/blob/master/include/uapi/linux/posix_acl_xattr.h),
[descriptor xattr errors](https://man7.org/linux/man-pages/man2/fgetxattr.2.html).
ABI interpretation is also tested by an independently compiled header-based
[oracle](../tests/fixtures/posix_root_abi.c), not Python constants alone.

Verification, macOS **15.1 / 24B83**, arm64, Python **3.12.14**, local APFS:

- **69 focused source tests passed in 0.893 seconds**, no skips: 18 new storage
  cases plus existing identity/wire/legacy and SQLite protection/cursor regressions.
- Storage fixtures cover real additional/inheritable ACL refusal, private modes,
  owner/context/type/closed-reference refusal, path substitution, borrowed state,
  compiled ABI and mount oracle, post-duplication and failed-entry cleanup,
  uncertain close/capacity, stale observations, malformed native buffers and inert
  public refusal. Real Linux ACL cases are defined but not executed on this Mac.
- Fresh dependency-free installed wheel: two legacy-byte tests passed; **119
  platform tests completed in 0.804 seconds**, **111 passed / eight native Windows
  tests skipped**. All 18 new storage cases passed from the wheel. Skips grant no
  native Windows admission. All three wheel storage modules match current source.
- Repository Ruff lint and format passed; Pyright reports zero errors/warnings;
  frozen Hatchling wheel/sdist build passed. Pinned build dependencies required
  network access outside the sandbox. Focused/artifact checks were rerun after the
  final capacity and mount-observation changes.
- CI YAML parses: required Ubuntu/macOS storage matrix runs source and fresh-wheel
  tests and requires the ABI compiler. Windows source/wheel tests explicitly cover
  inert public refusal. Full package smoke also copies the new tests and C fixture.
  These CI jobs are prepared, not run or admitted here.

Publication verification, 2026-10-04:

- Full `make check` passed with exit zero against implementation `3c2f98d`:
  **2,813 source tests in 2,383.618 seconds**, 12 skips, **86% coverage**;
  **2,058 fresh-wheel tests in 1,674.840 seconds**, eight skips. Ruff lint/format,
  Pyright, export verification and wheel/sdist builds also passed. Native Windows
  skips grant no qualification. Disposable logs remain outside Git.
- Current `main` advanced during the gate to `9822de6`. Integration commit
  `ce8cdc8` preserves both branches' package-smoke tests in the sole conflict.
  Post-integration source checks passed: **19 conversation-diff tests** in
  27.068 seconds, **16 Git/isolation tests** in 18.009 seconds, and **119 platform
  tests** in 1.092 seconds (eight native Windows skips). Ruff lint/format, Pyright,
  export verification and rebuilt wheel/sdist passed again.
- Fresh-wheel integration smoke passed the existing demo/replay, analysis and
  stdio/HTTP MCP setup, then **161 affected platform, legacy, diff and Git tests**
  in 43.772 seconds (eight native Windows skips). The temporary test selection
  used the integrated package-smoke harness; the tracked full suite is unchanged.

N-04/05/06 and the root portions of N-07/09/14/15 have focused native macOS and
portable fault evidence. Linux execution, other OS/build/architecture candidates,
and accountable boundary admission remain pending. The user authorized push and a
PR against `main` after the full gate. PR #272 remains open; prerequisite commits
are included until it merges. Publication does not enable public selectors,
enrollment or writers.

The subsequent [fixed-child reader candidate](POSIX_NAMESPACE_READ_WORK_NOTE.md)
implements bounded relative reads with fresh child entry/content/ACL checks and
owned cleanup. Next: complete accountable root/read target qualification/review,
then define the native Windows admission/read slice after its identity review.
Keep root selection, public reads, enrollment/custody, consumer adoption,
writers and public Windows selectors separately gated.
