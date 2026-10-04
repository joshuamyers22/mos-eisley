# Secure POSIX namespace record reads

Status: candidate implementation and full publication gate complete; reader CI and accountable admission pending. Owner: Josh Myers. Date: 2026-10-04.
Branch: `feat/posix-namespace-read`; baseline `9122242`, dependent on PR #273.

Implement the fixed-child read in [plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support)
and the [namespace contract](NAMESPACE_STORAGE_CONTRACT.md). The caller supplies
an owned POSIX directory lease. Return fresh advisory record metadata or typed
absence, without selecting a path, creating a record, enrolling a namespace,
adopting an existing store or enabling any public selector/writer.

Guidance: Python engineering and agentic verification guides, adversarial review
playbook, work-note/verification-loop/threat-model templates, ADR-0016.
Risk: material native-query and owned-reference boundary. Assets: namespace byte
integrity, root/child selection, private protection and reference lifecycle.
Untrusted retained records and concurrent same-owner changes must refuse when
observed; malicious kernel/admin/fully trusted same-owner process compromise is
outside the contract. Observations are not an atomic transaction or apply grant.

Blocking rubric: N-04 fresh principal; N-05 owned child cleanup/non-inheritance;
N-06 actual file owner/mode/ACL; N-07 fixed relative no-follow/nonblocking special
object and single-link refusal; N-08 held identity, entry and content mutation;
N-09 at most 4,097 requested bytes and 16 native read attempts, bounded ACL buffers;
N-10 typed absence only after fresh root/entry checks; N-14 additive legacy behavior;
N-15 real native source and dependency-free wheel evidence. Executable fault cases
and real filesystem fixtures decide candidate completion. Accountable target
admission remains separate. Ceiling: three corrective passes, two hours active
work; stop after affected source/wheel, lint/type and artifact checks pass. Run the
full `make check` gate before later publication. No live stores/sampling artifacts.

## Implementation and evidence

The direct [POSIX candidate](../src/mos_eisley/platform/posix_storage.py) exposes
`read_namespace_record(lease)` and the equivalent lease method. Only the literal
`identity-namespace.v1.json` is opened relative to the held root with
`O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`. Closed, stale, uncertain-release
and capacity-exhausted leases refuse before opening. The existing 64-reference
cap now includes transient children and uncertain ownership as well as root leases.

Fresh child fstat, actual descriptor ACL and filesystem observations require a
single-link regular file, exact 0600/0400 mode, current root owner and matching
device/filesystem/mount policy. Native queries are bracketed by fresh metadata and
principal checks. Non-following relative entry checks compare device/inode, type,
mode, owner/group, link count, size and nanosecond mtime/ctime before and after
reading. Root observations are repeated before opening, after reading and after
confirmed child release. Atime is excluded because ordinary reads may update it.

The [native read](../src/mos_eisley/platform/posix_storage_native.py) allocates at
most 512 bytes per request and performs exactly one libc call per attempt. Count
all requests, including EINTR, against at most 4,097 bytes total and 16 attempts.
Short reads continue within both budgets; early EOF, growth, exhaustion or unknown
native results refuse. This avoids the automatic EINTR retries documented for
[Python's `os.read`](https://docs.python.org/3.12/library/os.html#os.read).
Regular filesystem I/O has no wall-clock deadline; nonblocking open prevents FIFO
waiting and special objects refuse before content reads.

Strict canonical decoding and exact principal equality precede an advisory
`StorageCheckedNamespace` containing the record, root/child identities and SHA-256
of exact bytes. `NamespaceMissing` requires ENOENT on the fixed relative open,
confirmed entry absence and fresh root checks; it creates nothing. Malformed,
changed, bounded-capacity and open/query failures have stable exception categories,
without private payloads in diagnostics. Results hide private values in reprs.
These ordinary metadata values are forgeable and grant no apply/enrollment authority;
a future effect boundary must verify live state independently.

Every acquired child closes on success, refusal or cancellation, including partial
ownership-registration failure. A failed native close refuses success, retains
bounded uncertain ownership, disables root/child acquisition and is never retried.
Tests restore only deliberately injected fixture state; production has no reset API.

Final evidence on macOS **15.1 arm64**, Python **3.12.14**, local APFS:

- **141 affected source platform tests in 0.929 seconds**, eight native Windows
  skips. All **22 new reader tests passed**, including real descriptor ACL refusal,
  symlink/FIFO/socket/directory/multiple-link refusal, replacement/detachment,
  same-inode content mutation, original-path substitution, stale principal/root,
  owner/device/mount faults, exact-limit/overflow/short/EINTR bounds, non-inheritance
  and failed/partial cleanup.
- Dependency-free fresh installed wheel: **141 platform tests in 0.938 seconds**,
  eight native Windows skips; all 22 reader cases passed. Two frozen legacy-byte
  tests also passed in the wheel. Actual native Windows skips grant no admission.
- **Seven legacy-fixture tests in 1.602 seconds** and **two existing SQLite
  protection/cursor regressions in 0.040 seconds** passed from source.
- Repository Ruff lint/format passed; Pyright reports zero errors/warnings;
  frozen Hatchling wheel/sdist builds passed. All three changed platform modules
  match wheel bytes. CI YAML and source/wheel test-copy wiring checks passed.
- Required Ubuntu/macOS storage CI now includes the reader source tests and
  dependency-free wheel suite; Windows source/wheel checks include inert public
  refusal. Full package smoke includes the new tests. These new CI jobs were
  prepared, not executed here. The sandbox denied the Unix-socket fixture; final
  native runs used authorized execution outside it.

Review/fault evidence corrected a partial ownership-registration cleanup gap;
the regression verifies the opened child closes even when registration fails.
No remaining observed candidate blocker. Stop rule: affected native source/wheel,
fault, lint/type and artifact checks passed. Linux reader execution, other exact
target candidates and accountable root/read admission remain pending. Public
storage admission, public record reads, Windows selectors, enrollment/custody,
consumer adoption and writers stay closed. The full publication gate below
supersedes the earlier focused-only verification; push and PR are now authorized.

## Publication verification

Full `make check` passed with exit zero against implementation `99e6196`:
**2,842 source tests in 2,367.187 seconds**, 12 skips, **86% coverage**;
**2,096 fresh-wheel tests in 1,503.382 seconds**, eight skips. Ruff lint/format,
Pyright, runtime export verification and frozen wheel/sdist builds also passed.
Disposable output remains outside Git; native Windows skips grant no admission.

PR #273 remains open with all reported checks successful. Refreshed `main`
(`9822de6`) is already an ancestor of this branch; no integration commit is needed.
The reader PR targets `main` and includes prerequisite commits until they merge.
The verification-record commit changes documentation only. Linux reader CI and
accountable root/read admission remain pending; neither publication nor green
candidate checks enable public selectors, enrollment or writers.

Next: qualify/review the POSIX root/read candidates and define the smallest native
Windows admission/read candidate after its identity prerequisite review. Protected
anchor/key custody, locking/no-overwrite publication, durability and enrollment
remain independent later batches.
