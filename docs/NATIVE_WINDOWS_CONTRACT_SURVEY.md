# Native Windows contract survey and first implementation batch

- Date: 2026-10-03; owner: Josh Myers; review by: 2026-10-17
- Base: GitHub main `a1cb38bcfcbe332a7db2c22322fa72fb560db672`
- Scope: [plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support)
  and its §27.3 delivery sequence. This is a source/test survey and batch definition,
  not implementation or native Windows qualification.
- Working branch: `docs/native-windows-contract-survey`; isolated from the tmux
  and WSL2 preparation branches and the original checkout's plan amendment.
- Guidance: [architecture playbook](ADVERSARIAL_REVIEW_PLAYBOOK.md),
  [review/improvement template](../templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md),
  [Python guide](PYTHON_ENGINEERING_GUIDE.md), and
  [work-note template](../templates/WORK_NOTE.md).
- Bound: one survey/definition pass, 45 minutes, no provider calls or runtime
  changes. Stop after source-backed scope, acceptance criteria and documentation
  checks; real Windows evidence remains a separate implementation gate.

## Findings against current main

Native Windows support is a planned port, not a packaging switch. Existing narrow
interfaces are useful, but filesystem and principal assumptions still cross
application, storage and CLI boundaries. A text scan for UID, locking, file flags,
file identity and POSIX process/terminal operations matched 97 of 313 Python source
files (578 matches across 396 lines). These are migration leads, not 97 proven
defects: some operations already have guards or intentionally belong to adapters.

| §27.2 contract | Direct source/test evidence | Gap and next boundary |
|---|---|---|
| Platform services | [bounded reader](../src/mos_eisley/run/files.py), [conversation store](../src/mos_eisley/run/conversation_store.py), [process plumbing](../src/mos_eisley/run/process.py) each call OS APIs directly | Introduce one operation-specific contract and qualify its POSIX adapter before moving another responsibility |
| Principal/schema migration | [conversation state](../src/mos_eisley/conversation_state.py), [memory](../src/mos_eisley/conversation_memory.py), [guidance](../src/mos_eisley/project_guidance.py), [SQLite](../src/mos_eisley/run/conversation_sqlite.py) persist or compare integer `owner_uid` | Tagged UID/SID identities, legacy decoding and hash-preserving explicit owner rebinding require their own migration batch |
| Private storage | Conversation store checks UID, mode, link count, descriptor identity, `dir_fd` and `flock`; memory/SQLite have their own related checks | Owner/DACL policy, handle identity, reparse rejection, locks, replacement and durable flush need a reviewed NTFS implementation, not renamed POSIX constants |
| Paths/Git | [workspace selection](../src/mos_eisley/conversation_project.py) and [directory UI](../src/mos_eisley/conversation_directory.py) use existing host paths; store operations rely on POSIX descriptors | Define Windows namespace validation and distinguish user-selected paths from archive names; actual Windows Git/worktree qualification follows storage/process contracts |
| Terminal/credentials | CLI, directory selector and picker import `termios`; [operator input](../src/mos_eisley/operator_review_cli.py) uses `add_reader`; [OAuth store](../src/mos_eisley/tools/mcp_oauth_store.py) imports `fcntl` and explicitly selects only macOS/Linux keyrings | Existing credential protocol can be reused, but Windows credential selection, serialization, console input and cancellation still need implementation |
| Process lifecycle | [watchdog](../src/mos_eisley/run/watchdog.py) uses `pass_fds`, `start_new_session` and pipe selectors; process plumbing drains subprocess pipes with selectors | Job Object descendant supervision, non-inheritable handles and native pipe draining require a distinct lifecycle batch |
| Containment | [offline container](../src/mos_eisley/run/isolation.py) depends on reviewed Docker daemon/image and Linux worker constraints | This supplies no native restricted-token/AppContainer/Job Object enforcement or native filesystem/network attestation |
| Package/release | [CI](../.github/workflows/ci.yml) runs source/package/container jobs on Ubuntu; [wheel smoke](../tools/smoke_package.py) uses `venv/bin/python` | Add scoped native jobs during port development; full wheel/CLI parity and every advertised Windows release target remain final qualification gates |

There are eight modules with top-level `fcntl` imports and three with top-level
`termios` imports in this snapshot. The [CLI](../src/mos_eisley/cli.py) loads
conversation command registration, which reaches these platform-dependent modules.
Consequently, an isolated contract import test is not evidence that `mos --help`
or conversation startup works natively.

Python documents [fcntl as Unix-only](https://docs.python.org/3.12/library/fcntl.html),
[OS feature availability](https://docs.python.org/3.12/library/os.html), and
[Windows asyncio limitations](https://docs.python.org/3.12/library/asyncio-platforms.html).
These support the portability findings; no native execution was attempted here.

## Smallest implementation batch: bounded regular-file read contract

**Recommended branch:** `refactor/platform-bounded-read`.

Preserve the existing `run.files.read_bounded(path, limit=2_000_000) -> bytes`
entry point while moving its one OS-specific operation behind a small, typed
platform boundary. It is referenced in 69 source files including its defining
module; preserving that API avoids editing those consumers and changing their
replay/hash behavior. It does not require persisted principal migration because
the current reader is not a private-owner validation operation.

Proposed footprint (names may be adjusted to repository conventions):

| File | Change |
|---|---|
| `src/mos_eisley/platform/files.py` | Define a narrow bounded regular-file reader contract, explicit platform selection and a safe unsupported-platform failure; keep import-time work inert |
| `src/mos_eisley/platform/posix_files.py` | Implement existing open/descriptor/type/bound/cleanup behavior using actual POSIX APIs |
| `src/mos_eisley/run/files.py` | Preserve the public wrapper and default; delegate to the selected adapter |
| `tests/test_platform_files.py` | Isolated invariant, real POSIX and unsupported-native-platform tests; do not import the CLI |
| `tools/smoke_package.py` | Include the isolated tests in installed-wheel verification |
| `.github/workflows/ci.yml` | Add a narrowly scoped Windows-native installed-wheel import/refusal job; retain existing full Ubuntu checks |

Use a function or structural protocol instead of a service locator or universal
filesystem class. Only the selected adapter imports platform-specific facilities.
An unsupported Windows path must fail before opening/reading a file; do not remove
`O_NOFOLLOW` or fall back to ordinary `Path.read_bytes()` to make it run.

### Contract and acceptance checks

1. Preserve byte-for-byte results for existing valid callers: empty files,
   exact-limit input, explicit/default bounds and ordinary regular files. Define
   nonnegative integer limit admission (including empty-file behavior at zero);
   reject invalid limits before I/O so they cannot trigger an unbounded read.
   Record this deliberate invalid-input tightening separately from extraction.
2. Preserve final-component symlink refusal and opened-descriptor regular-file
   verification. Directories and FIFOs reject; FIFO rejection must complete under
   an external test timeout rather than relying on a test that might hang.
3. Read no more than `limit + 1` bytes and reject overflow without silently
   truncating. Close descriptors on success, overflow, type rejection and read
   failure. Fault-injection tests verify these cleanup paths.
4. Characterize and preserve existing `OSError`/`ValueError` behavior used by
   callers. Race tests substitute the final component between lookup/open and
   verify refusal or validation of the actual opened object; do not replace the
   atomic no-follow open with an `lstat`-then-ordinary-open check.
5. Preserve the reader's actual scope: it does **not** authenticate ownership,
   reject ordinary hard links, guarantee immutable content, or reject every
   ancestor symlink. Those are distinct private-storage/rooted-open contracts.
   Explicitly characterize allowed ancestor traversal so extraction cannot be
   mistaken for new containment or silently break existing paths.
6. On native Windows, the new contract/wrapper must import without accessing POSIX
   constants or loading a POSIX adapter. Its unsupported operation must refuse
   before I/O; tests must assert refusal rather than skip the Windows boundary.
   This isolated job does not run or qualify the full CLI.
7. Run the shared tests against source and the installed wheel on macOS/Linux.
   Run the scoped installed-wheel import/refusal test on a real native Windows
   runner. Mocks alone do not establish native import/selection behavior.
8. Run focused reader/store/replay tests, lint, typing and the full combined
   `make check` before publication. Record skips and any existing fixture failures;
   never relabel an unsuccessful combined invocation as passing. Require the new
   native job and existing CI gates before merging the implementation batch.

The existing [store/CLI tests](../tests/test_store_cli.py) already exercise symlink,
FIFO and overflow rejection and recorded save/replay. New isolated tests are
needed because that module imports the full POSIX-coupled CLI. Add characterization
tests before moving code, then check affected replay consumers; add no schema,
credential, execution or model-authority changes in this batch.

Owner: Josh Myers. Initial ceiling: three correction passes/two hours of active
implementation, with long existing quality gates recorded separately. Stop on
passing invariants and gates; any need to weaken link/type/bound behavior or add a
native storage implementation expands this batch and requires a new scope.
Rollback: restore the existing `run/files.py` implementation and remove only the
new adapter/tests/scoped job. Existing artifacts remain byte- and schema-compatible.

## Dependency order after the first batch

| Order | Next bounded batch | Dependency and exit evidence |
|---:|---|---|
| 1 | Bounded-reader contract and qualified POSIX adapter | Existing reader/replay behavior; actual native import/refusal evidence, as defined above |
| 2 | Principal and file-identity contracts | Distinguish UID from SID and POSIX device/inode from Windows volume/file ID; pure validation plus real current-principal/handle tests; no automatic rebinding |
| 3 | Identity/schema compatibility and explicit migration | Version affected artifacts, retain legacy bytes/hashes, test same-owner replay and explicit authenticated rebinding; freeze migration acceptance before writers change |
| 4 | One private storage lifecycle, then SQLite/memory adoption | Reviewed NTFS DACL/rooted-handle policy, links/substitution, locks, atomic replacement and durable flush; real native adversarial tests and legacy replay |
| 5 | Native terminal and credential adapters | Qualified private identity/storage; console renderers, refresh/logout serialization and native secret-store refusal tests |
| 6 | Process supervision and Windows path/Git integration | Handle isolation, complete descendant cleanup, namespace validation and actual Git/worktree behavior; preserve execution/VCS authority gates |
| 7 | Native containment | Enforce and attest the common filesystem/network/resource policy; real positive/negative escape tests |
| 8 | Full installed-wheel parity and release qualification | Every applicable §27.2–27.3 suite on each advertised native Windows target; exact artifact and accountable review |

The future Windows reader/storage adapter must be designed around real handles and
namespace policy. Microsoft's [CreateFileW documentation](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
explains reparse-point open behavior; using a flag alone does not supply the full
rooted-directory or DACL contract. Microsoft also documents
[handle-based file identity](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information).
Neither POSIX mode bits nor a file-ID tuple alone establishes Windows private
ownership or isolation. These are future design inputs, not an implemented adapter.

## Survey verification and handoff

Inspected the plan, current primitive and representative consumers/tests, CLI
imports, storage/credential/process implementations, packaging and CI. Verified
primary platform documentation and local document targets. No code, schemas,
dependencies, CI jobs or runtime defaults changed; no execution suite or native
qualification was run for this documentation-only survey. The first batch remains
**defined, not implemented**. It can proceed independently of actual WSL2 runner
qualification and the separate tmux/WSL2 preparation PRs.
