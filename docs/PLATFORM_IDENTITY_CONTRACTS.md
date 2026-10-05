# Principal and opened-file identity contracts

Status: tagged values, additive POSIX queries and candidate Windows principal
queries implemented; native qualification, native file queries and consumer/schema
adoption remain pending. Local POSIX verification is recorded in
[the implementation work note](PLATFORM_IDENTITY_IMPLEMENTATION_WORK_NOTE.md). Owner: Josh Myers. Scope: the next bounded batch under
[plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support),
after the [bounded-reader extraction](BOUNDED_FILE_READER_CONTRACT.md).
[ADR-0014](adr/0014-platform-identity-contracts.md) records the proposed design.

A [candidate Windows principal adapter](WINDOWS_PRINCIPAL_WORK_NOTE.md) now
implements process TokenUser acquisition for direct native qualification. The
public Windows selector still refuses pending actual native evidence and
accountable admission; native file identity remains unimplemented.

## Observed boundary and scope

| Existing consumer | Observed identity use | Compatibility obligation |
|---|---|---|
| [Conversation state](../src/mos_eisley/conversation_state.py) and [guidance](../src/mos_eisley/project_guidance.py) | Integer `owner_uid` in validated models | Preserve original canonical bytes, field names and hashes |
| [Conversation store](../src/mos_eisley/run/conversation_store.py) | `getuid`, `fstat` owner/type/mode/link checks, device/inode root checks, locks and snapshot hashes | Identity extraction cannot replace private-storage or integrity checks |
| [Memory](../src/mos_eisley/conversation_memory.py) | Same-owner documents; device/inode root/lock observations in reviewed previews | Preserve preview identities and apply hashes until versioned migration |
| [SQLite](../src/mos_eisley/run/conversation_sqlite.py) | Integer owner metadata, device/inode root comparison before SQLite opens its own descriptors | Identity query does not bind SQLite's separately opened connection |
| [Directory selection](../src/mos_eisley/conversation_directory.py) and [relocation](../src/mos_eisley/conversation_memory_identity.py) | Resolved path plus device/inode, retained in selection/receipts | Keep workspace keys and historical relocation receipts exact |

Separate identifier representation, current-principal discovery and opened-object
inspection from authorization. A matching identifier alone proves neither private
access nor content integrity. Keep permissions/DACLs, object type, hardlink policy,
namespace admission, locking, durable writes and snapshot verification at their
existing storage boundaries. There is no migration or cross-platform resume in
this additive slice.

## Value types and equality

Use immutable, strictly validated standard-library value objects. The following
names and fields are the runtime API, not new persisted schemas. Tagged
variants form discriminated unions; no optional UID/SID bag, implicit conversion,
Pydantic/storage dependency, or universal platform service locator is needed.

| Variant / fixed `kind` | Payload and validation | Equality |
|---|---|---|
| `PosixPrincipal` / `posix-uid` | `uid`: exact built-in integer, nonnegative; reject bool, float, text and sentinel negatives | Kind and full UID |
| `WindowsPrincipal` / `windows-sid` | `sid`: immutable binary SID, copied out of validated native storage; revision 1, 0–15 subauthorities, exactly `8 + 4 * count` bytes (8–68 bytes), no trailing bytes; reject mutable buffers and text aliases | Kind and all SID bytes |
| `PosixFileIdentity` / `posix-file` | `device`, `inode`: exact nonnegative integers, no bool/coercion/truncation | Kind and both fields |
| `WindowsFileIdentity` / `windows-file` | `volume_serial`: exact integer in `[0, 2**64)`; `file_id`: exactly 16 immutable bytes in native returned byte order | Kind, full volume serial and all 128 file-ID bits |

`PrincipalIdentity = PosixPrincipal | WindowsPrincipal` and
`FileIdentity = PosixFileIdentity | WindowsFileIdentity`. Distinct kinds never
compare equal even when numeric pieces happen to match. No truncation to a Windows
RID, UID, 32-bit volume field, or 64-bit file ID is allowed. Unknown tags, missing
fields and extra fields are rejected by any explicit future decoder; there is no
best-effort reconstruction. Plain value construction performs no OS calls.

Binary SID equality avoids account-name lookup and textual alias normalization.
Future native acquisition must first prove the SID header/body lie in the owned
buffer, then validate with `IsValidSid`, obtain the exact length, copy
into bounded owned bytes, then release native storage. The portable validator must
check the same structural bounds without dereferencing an untrusted pointer.
The implementation tests must fix revision/count/length boundaries against native
validation; unsupported SID revisions are refused rather than repaired.
[Microsoft describes SID structure and validation](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-sid),
[IsValidSid](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-isvalidsid),
[GetLengthSid](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getlengthsid)
and [the maximum subauthority count](https://microsoft.github.io/windows-docs-rs/doc/windows/Win32/System/SystemServices/constant.SID_MAX_SUB_AUTHORITIES.html).

Equality is identifier equality within one explicitly established host/account or
filesystem namespace. It is not globally scoped ownership. Numeric UIDs can repeat
across machines and namespaces; copying an artifact does not establish common
scope. These value objects deliberately carry no invented machine GUID or migration
credential. Callers must establish the scope before an ownership comparison; a
future persistent envelope and authenticated rebinding belong to the next batch.

File IDs describe an observed object, not a path, snapshot digest, generation,
lease or permanent identifier. Compare fresh observations while both references
are live on the same host/filesystem context. Do not use a closed observation to
admit a reopened object merely because its numbers match: IDs may be reused after
deletion. Rename and hardlink aliases of the same live object should compare equal;
newly replacing its pathname with another live object should compare unequal.
Content may change without any identity change. These scope/lifetime restrictions
are caller preconditions, not guarantees supplied by value equality.
[Microsoft's handle information documentation](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information)
describes file-ID lifetime limitations.

## Narrow query APIs

```python
# Implemented POSIX queries; Windows/unknown platforms explicitly refuse.
def current_principal() -> PrincipalIdentity: ...
def file_identity(opened: PosixDescriptor | WindowsHandle) -> FileIdentity: ...
```

`PosixDescriptor(fd: int)` and `WindowsHandle(value: int)` are distinct borrowed
reference types. Validate exact integer type/range before a syscall: POSIX descriptors must fit
the qualified platform's nonnegative C `int` range (0 through `2**31 - 1` on the
initial macOS/Linux targets). Windows handles must fit the native unsigned pointer
width, excluding zero and the all-ones `INVALID_HANDLE_VALUE`; reject bool,
negative values and overflow.
A CRT file descriptor is not a Windows HANDLE. Never infer which it is from an
integer or convert it implicitly. The caller owns and keeps the reference alive
through the query; the query never closes it, changes its inheritance/offset, reads
content, acquires a lock, opens a pathname or writes state. Reuse of a descriptor
number after closing it violates that lifetime precondition.

On a selected platform, wrong reference kinds fail before an OS call. Importing
contracts or wrappers performs no I/O, principal query, DLL loading or adapter
selection. Adapter imports are lazy and explicit, like the reader contract.
Unsupported platforms or unqualified adapters fail closed without fabricating an
identity. No environment variable or username fallback is allowed.

### POSIX acquisition

- `current_principal` reads `os.getuid()` for the real UID, preserving the meaning
  of existing `owner_uid` comparisons. It also checks `os.geteuid()` and refuses a
  real/effective UID mismatch in this initial contract; it does not silently switch
  to an effective or saved UID. This stricter context admission applies only to the
  new API until consumer adoption is separately reviewed. UID 0 is a valid value;
  it does not imply an unprivileged process. Group/capability policy remains a
  separate authorization responsibility.
- `file_identity` uses a single `os.fstat(fd)` result for the supplied live
  descriptor, accepts regular files/directories and returns its full device/inode.
  Reject other object types. Do not use `stat(path)` or `lstat` followed by reopen.
  Identity inspection cannot tell whether admission earlier followed a symlink.
- No adapter cache may hide a changed principal; query on each request. Callers
  that span effects must revalidate context and retain opened references under
  their established storage/lifecycle policy. Namespace or credential switching
  during an operation is unsupported; this query does not create an atomic lease.

Python documents [real UID](https://docs.python.org/3.12/library/os.html#os.getuid),
[effective UID](https://docs.python.org/3.12/library/os.html#os.geteuid) and
[descriptor inspection](https://docs.python.org/3.12/library/os.html#os.fstat).

### Native Windows acquisition and qualification target

- Obtain the current process token's `TokenUser` SID with query-only rights, not
  `TokenOwner`, a group SID, username, environment data or logon/session ID.
  Elevation can change privileges while retaining a user SID; equality never
  implies equal privilege or access.
- The initial owner context does not support thread impersonation. Check for a
  thread token and refuse if present. Only `ERROR_NO_TOKEN` permits proceeding to
  the process token; access denied, anonymous-token and other failures must not
  trigger that fallback. Do not silently call `RevertToSelf` or change privileges.
  Recheck the no-impersonation/context precondition at effect boundaries; the query
  does not guarantee subsequent security context stability.
- Query `GetTokenInformation(TokenUser)` with bounded allocation (at most 64 KiB,
  at most two query attempts after sizing); verify returned pointer/length stay
  inside the owned buffer before copying the SID. Close every temporary token
  handle and free temporary allocation on every exit; do not close caller handles.
- Query the supplied live file/directory handle with
  `GetFileInformationByHandleEx(FileIdInfo)` and preserve `FILE_ID_INFO`'s 64-bit
  volume serial and 128-bit ID. Validate object/filesystem eligibility from handle
  observations; the initial qualified target is local NTFS. Refuse remote,
  removable or other unqualified filesystems, non-disk objects and failed or
  unsupported identity queries. Do not fall back to names, timestamps, hashes,
  Python inode approximations or zero-extending another API's narrower ID.
- Handle queries do not qualify secure path opening. Reparse rejection, rooted
  namespace policy, DACL admission, sharing modes and destructive operations
  remain the storage adapter's responsibility. A query cannot prove that an
  already-opened object was admitted under those policies.

These are project design requirements derived from the platform APIs, not claims
that adapters exist. Microsoft documents
[thread token access and cleanup](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openthreadtoken),
[token information](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation),
[FileIdInfo queries](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex)
and [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info).
Advertised Windows version/architecture coverage and local-NTFS detection must be
recorded and tested when the native adapter is implemented; API availability alone
does not qualify a target.

### Failures

| Condition | Required result |
|---|---|
| Invalid value/reference input | `ValueError` before I/O; no coercion or repair |
| Wrong reference kind on a qualified platform | `ValueError` before querying |
| Unsupported platform or adapter | Existing `UnsupportedPlatformError` (`OSError` subclass), before platform I/O |
| Ambiguous/unsupported principal context | `IdentityContextError` (`OSError` subclass); no alternate principal |
| Closed handle, access/query failure | `IdentityQueryError` (`OSError` subclass), safe stable message and preserved exception cause; no partial identity |
| Ineligible object/filesystem or unavailable full-width ID | `IdentityQueryError`; no synthetic fallback |

Validate input first, then select a qualified adapter, then check reference kind and
query. Messages must omit paths, SID/UID values, usernames and native token details;
causes stay diagnostic and are not directly rendered by CLI error handlers. No
identity material or authority-bearing OS handle belongs in routine telemetry.

## Legacy boundary and subsequent migration

The additive POSIX implementation adds inert modules, tests and scoped wheel/CI
coverage only; it does not adopt the APIs into existing callers. Existing call sites,
`owner_uid`, SQLite metadata schema, `device`/`inode` receipt dictionaries,
canonical serialization, workspace keys, apply hashes and snapshot hashes stay
unchanged. Do not serialize these new objects into an existing schema or coerce a
Windows SID into an integer field. Legacy decoders remain in place and reject
unsupported cross-platform ownership rather than inventing a mapping.

The following migration batch must enumerate every affected artifact and choose
versioned host/account binding, legacy decoding and explicit authenticated owner
rebinding. Original signed/canonical bytes and verification hashes stay verifiable;
no on-read rewriting or silent replay under a different principal is allowed.
This contract cannot supply cross-host authentication or migration authority.

## Acceptance matrix for implementation

I-01–I-05 and additive compatibility checks are exercised by the POSIX slice;
[the implementation work note](PLATFORM_IDENTITY_IMPLEMENTATION_WORK_NOTE.md) records
actual results. The [candidate Windows principal record](WINDOWS_PRINCIPAL_WORK_NOTE.md)
adds source/wheel qualification tests. I-06–I-08 remain native qualification
gates; actual native CI for this candidate remains pending publication.

| ID | Evidence | Blocking threshold |
|---|---|---|
| I-01 | Portable construction and equality tests | Reject bool/text/float/negative inputs, wrong tags, malformed/truncated/overlong SID and IDs, mutable buffers, volume overflow; compare all bits and never conflate kinds |
| I-02 | Clean-process imports with POSIX APIs/DLL loader made unavailable | No I/O or eager adapter load; unsupported requests explicitly refuse; exercised from source and fresh installed wheel |
| I-03 | Real macOS/Linux current-principal queries plus injected mismatches | Match independent `getuid`; unequal real/effective UID refuses; changed responses not cached; environment/username spoofing ignored |
| I-04 | Real opened POSIX file/directory, duplicate FD, hardlink, rename and replacement | Same live object equal, distinct live replacement unequal; query leaves caller descriptor usable and offset unchanged; one fstat sample per query; no pathname access |
| I-05 | Closed/negative/wrong-kind refs, special objects and query fault injection | Typed refusal without hangs, partial identities, caller-handle closure or leaks; borrowed-reference lifetime documented |
| I-06 | Native Windows current-user token with independent native SID comparison | Exact SID bytes, no impersonation fallback except absence, thread-token refusal, pointer/buffer bounds and cleanup; elevated same-user SID is not an authorization pass |
| I-07 | Native local-NTFS file/directory handles, duplicate handle, hardlink, rename and replacement | All volume/file-ID bits preserved, borrowed handle/position unchanged; no fake path/64-bit-ID fallback; IDs observed while original objects remain held |
| I-08 | Native error and eligibility tests | API failure, closed handle, pipe, remote/non-NTFS/unqualified storage and malformed buffers fail closed; mocked faults supplement actual native token/file queries |
| I-09 | Legacy compatibility and packaging | Existing source/wheel suites pass; representative JSON/memory/SQLite/guidance fixtures retain exact bytes and hashes; new tests included in wheel smoke; no CLI/native reader qualification claim |

Do not force impersonation, elevation or unavailable filesystem fixtures to pass by
skipping them silently. Record unavailable cases and keep their qualification gate
open; ordinary hosted CI can supply baseline native evidence, with owner-operated
fixtures for contexts it cannot create. SID and file-ID oracle tests must compare
against an independent native query, not the adapter being tested.

## Smallest implementation order

1. Add pure tagged values and borrowed reference validation, with isolated tests.
2. Add lazy POSIX principal/file queries and explicit Windows/unknown-platform
   refusal. Run I-01–I-05 and I-09 from source and installed wheels; extend the
   scoped native job to exercise pure types and explicit refusal. Keep current
   consumers and artifacts unchanged. This is the first implementation PR.
3. Implement native read-only token/file identity adapters with bounded native
   resources and I-06–I-08 on actual Windows/local NTFS. Freeze and review filesystem
   detection and supported targets before admitting the native selector. This is a
   separate implementation PR, with owner/domain review for the boundary.
   The first sub-batch implements only candidate principal queries on AMD64
   Windows build 17763+ with 64-bit CPython 3.12+, native oracle/impersonation/cleanup
   tests and source/wheel CI. Native selector admission is separate from this
   candidate implementation; local-NTFS file queries are the next sub-batch.
4. Migration inventory/design may proceed alongside adapter qualification. Change
   versioned writers and adopt one private-storage lifecycle only after both
   adapters qualify and migration acceptance is frozen. No broader storage replacement
   or reader fallback belongs to these identity PRs.

Implementation footprint for the POSIX slice: `platform/identity.py`, `platform/posix_identity.py`,
an isolated `tests/test_platform_identity.py`, wheel smoke inclusion and scoped CI
updates. Add a Windows adapter only in step 3. New modules should use the standard
library and depend on no CLI/store; avoid changing the stable bounded-reader API.
Rollback before adoption removes these additive modules/tests/jobs without touching
retained data. No automatic rebinding, dispatch or execution authority is added.

## Candidate Windows principal usage

For qualification on the candidate native target only:

```python
from mos_eisley.platform.windows_identity import current_principal

principal = current_principal()
```

This direct entry point queries the process TokenUser with TOKEN_QUERY rights,
refuses thread tokens before and after acquisition, and returns copied bounded
SID bytes. Only ERROR_NO_TOKEN permits proceeding to the process token. Temporary
token handles close on every exit; no context or privilege is changed. No SID is
logged. Bounds precede native IsValidSid/GetLengthSid calls on an owned SID copy.
The host guard rejects other architectures, 32-bit processes and older Windows
builds before DLL loading. This candidate target range is not a qualification
claim for every version; hosted CI records its actual version/architecture.

The common `platform.identity.current_principal` continues to reject Windows;
effect-boundary context revalidation, accountable selector admission, native file
identity, storage authorization and consumer/schema adoption remain separate.
See [the work note](WINDOWS_PRINCIPAL_WORK_NOTE.md) for actual results and pending
native evidence. API availability or mocked success does not close I-06/I-08.

## POSIX slice usage

```python
from mos_eisley.platform.identity import (
    PosixDescriptor,
    current_principal,
    file_identity,
)

principal = current_principal()  # Fresh real UID; unequal effective UID refuses.
# Borrow an already admitted, live file/directory descriptor from the caller:
identity = file_identity(PosixDescriptor(fd))
```

The caller retains ownership of `fd`. The query performs one fstat, never reads,
opens a path, closes the descriptor or changes its offset/inheritance. References
must be instances of the exact defined borrowed-reference classes; arbitrary ints
and reference subclasses are not an alternative query interface. Value/reference
reprs omit payloads. No decoder, persisted envelope or existing consumer migration
is introduced. Pure binary SID construction validates structure, not account
existence or token provenance; native validation/query qualification remains open.

The existing scoped `windows-files` wheel job also selects portable identity value
and import/refusal tests, without selecting POSIX tests. It now executes fourteen
common tests across reader and identity contracts; this does not qualify Windows
identity queries, native reading or the full CLI. On macOS/Linux the isolated helper
runs thirty reader/identity tests; the main wheel smoke includes all identity tests.
