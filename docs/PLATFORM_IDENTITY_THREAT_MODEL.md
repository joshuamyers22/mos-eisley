# Principal and file-identity boundary threat model

## Scope and ownership

Owner: Josh Myers. Date: 2026-10-03. Baseline: f8a8e94. Review trigger: implementation
of [the defined identity contracts](PLATFORM_IDENTITY_CONTRACTS.md), native adapter
admission, or consumer/schema adoption. This is design preparation; accountable
boundary review and native qualification remain pending.

The [candidate principal implementation](WINDOWS_PRINCIPAL_WORK_NOTE.md) now adds
direct native TokenUser acquisition, with source/wheel fault and qualification
tests. The common Windows selector remains closed pending actual native evidence
and accountable admission. Native file identity and storage policy remain open.

In scope: identifier inputs, OS token/descriptor observations, native query buffers
and borrowed/temporary handle lifetime. Out of scope: implementing DACLs, secure
namespace opens, writes/locking/durability, migration, provider calls or execution.

## Assets, actors and boundaries

| Asset | Need | Boundary |
|---|---|---|
| Retained owner and file observations | Correct interpretation; no unauthorized rebinding | Untrusted retained input versus validated local OS observations |
| Live caller-owned references | Remain usable, correctly typed and unclosed by queries | Borrowed fd versus HANDLE; ownership/lifetime stays with caller |
| Temporary token handles and buffers | Bounded allocation, safe pointer access and cleanup | Native API/FFI versus owned Python values |
| Legacy snapshots and receipts | Byte/hash preservation | Additive values versus existing codecs and SQLite metadata |

Actors include a local path-replacement adversary, malformed identity input, stale
or closed-reference callers, and a changed/impersonating security context. Kernel
observations assume the selected OS is trusted; malicious administrator/kernel
behavior is outside this primitive's isolation guarantee. No new external service
or third-party runtime dependency is proposed. SID/UID values can identify people;
routine logs must omit them. This metadata confers no authorization.

## Abuse cases and controls

| Abuse | Consequence | Required control/evidence | Residual limit |
|---|---|---|---|
| SID/RID/UID or device/volume conflation | Wrong owner/object comparison | Tagged strict values, full-width equality, I-01 | Same numerical UID across hosts is still not authenticated common scope |
| Environment spoofing or impersonation fallback | Wrong current principal | Native OS queries only; mismatch/impersonation refusal, I-03/I-06 | Context can change after a query; effect boundary must revalidate |
| Path substitution between stat/open | Identity attached to a different object | Query only supplied live reference, I-04/I-07 | Query does not qualify the original path admission |
| Reused inode/ID or fd number | Stale observation accepted | Compare while original references remain held; never admit from stale values, I-04/I-05 | Value alone has no permanent lifetime or content guarantee |
| Hardlink or unchanged-ID content mutation | Privacy/integrity falsely inferred | Keep link/permission/DACL and digest policy separate, I-09 | Same-object equality intentionally accepts aliases |
| Truncated native ID or malformed SID pointer | Collision or memory fault | Full-width layout, bounds before native SID validation, I-01/I-06/I-07 | Native ABI/layout must be validated on each advertised architecture |
| Query failure treated as missing/zero identity | Unsafe continuation | Typed explicit error, no synthetic fallback, I-05/I-08 | Caller must preserve refusal in its own error path |
| Unbounded native sizing or leaked token handle | Resource exhaustion | 64 KiB allocation ceiling, bounded retries and cleanup tests, I-06/I-08 | Hosted CI alone cannot cover every privilege/storage configuration |
| Query closes/reopens borrowed reference | Wrong object, offset or use-after-close | Never close, read, reopen or mutate caller reference; I-04/I-05/I-07 | Caller must prevent concurrent close/reuse |
| New value serialized into old artifact | Invalid hashes/rebinding | Keep codecs/writers unchanged; exact legacy fixture evidence, I-09 | Future persistence requires its own accepted migration contract |

## Decisions and recovery

No new accepted privacy or authorization exception is granted. Equality is
contextual metadata. DACL/permission admission, namespace containment and privilege
policy remain separate responsibilities; their native implementations are open.

Implementation must retain independent native principal/file-ID oracle tests,
negative/fault tests and source/wheel compatibility checks. Any unavailable native
case is reported as pending, not passed. Native API behavior, account scope or
schema semantics that cannot meet the contract trigger a separate reviewed design.

Before adoption, rollback removes additive modules and CI/tests without rewriting
artifacts. After adoption, migration/recovery dependencies must be reviewed in the
following schema batch. These records contain no credentials, retained private
payloads or new dispatch authority.

## Candidate principal controls

Only the guarded direct qualification entry point loads `kernel32.dll` and
`advapi32.dll`, using `LOAD_LIBRARY_SEARCH_SYSTEM32` and explicit pointer-sized
HANDLE/fixed-width DWORD/BOOL signatures. DLL bindings are initialized once under
a lock and retained for process lifetime; tokens, buffers, contexts and identifiers
are never cached. Candidate coverage is 64-bit AMD64
Windows build 17763+; versions/architectures absent from actual native evidence
are not qualified by this guard alone.

Thread tokens are inspected with query-only rights and OpenAsSelf; presence
refuses, and errors other than ERROR_NO_TOKEN refuse without process fallback.
The precondition is checked again before returning the copied SID. The adapter
never impersonates, reverts context, changes privileges or logs identifiers.
Native impersonation fixtures run in disposable child processes with cleanup.

TokenUser sizing requires an insufficient-buffer response, caps each allocation
at 64 KiB, and allows at most two data queries. Returned structure/header/body
bounds precede any SID validation; IsValidSid/GetLengthSid inspect an owned bounded
copy. Temporary thread/process handles close even on malformed buffers, query
errors, allocation failures and final-context refusal. Cleanup failures refuse
rather than returning a successful observation. Fault tests supplement native
SID-oracle and handle-count tests; they do not qualify the API on macOS.

## Candidate opened-file controls

The direct candidate entry point validates an exact WindowsHandle and the same
AMD64/build-17763+ target before lazy trusted System32 kernel32/ntdll binding.
GetFileType, FileFsDeviceInformation, GetVolumeInformationByHandleW and
FileStandardInfo establish the frozen observed disk/local-NTFS file/directory
scope. Unknown characteristics and removable, remote, virtual, Terminal Services,
WebDAV, portable or clustered storage refuse. Device flags do not prove physical
hardware provenance or safe future private storage. Native rejection fixtures
beyond ordinary local NTFS CI remain pending owner-operated evidence.

FileIdInfo returns the complete 64-bit serial and 128-bit ID without fallback.
Only fixed-size owned output structures and a 261-character filesystem buffer are
used. No path/volume namespace lookup, file opening/reading, borrowed-handle close,
position or inheritance mutation occurs. The caller must prevent concurrent
close/reuse; this adapter cannot make a handle lease from an integer wrapper.
An unexpected pending native volume query is refused, retaining one output-buffer
pair for process lifetime and disabling further device queries to prevent deferred
writes into freed storage and unbounded quarantine growth. No wait/cancel is issued.

Fault tests cover full-width ABI, eligibility order, native failures/malformed
completions, pending lifetime, bounded names, inert import and fresh identities.
Independent raw native marshalling, live duplicates/hardlinks/renames/replacement,
content mutation, directories, inherited-handle/offset preservation and real
pipe/closed-handle refusal run in disposable native processes from source/wheels.
These tests do not qualify Windows on a macOS host. Public selectors and all
consumer schemas/storage authority remain unchanged pending accountable admission.

## Proposed migration boundary

The [inventory](IDENTITY_MIGRATION_INVENTORY.md) and
[design](IDENTITY_MIGRATION_DESIGN.md) extend preparation to versioned persistence;
they implement no storage effects. Accountable design review remains open.

| Abuse | Required control and future acceptance | Residual limit |
|---|---|---|
| Relabel UID/SID or copy an owner namespace to impersonate a source | Strict tagged bindings, explicit protected enrollment and role-bound trust; M-02/04/14 | Namespace metadata alone authenticates nothing; malicious administrators are outside the primitive guarantee |
| Rewrite a leaf owner while keeping enclosing version/hash | Preserve raw/canonical bytes, new family versions and complete reference closure; M-01/03/05 | Historical bytes remain evidence under their original context, not destination authority |
| Reuse a reviewed preview after migration or change bytes without changing file ID | Fresh locked effect-boundary revalidation; new store generation and selection kinds; M-09/11/12 | Qualified path/storage/lock contracts are still required |
| Crash or replay an import to overwrite or duplicate committed state | No-overwrite publication, bounded durable commit/nonce state, exact receipt recovery; M-08/10/14 | Flush uncertainty is reported, never asserted to be rollback |
| Transfer task approvals, uncertain attempts or compaction context | Historical-only original records; rebuild destination active context through existing gates; M-13 | Migration cannot authorize execution, continuation or paid retries |
| Change OAuth UID-dependent keys to retrieve another account or leak tokens | Separate keychain namespace/relogin workflow; no credential access in artifact migration; M-15 | Native credential custody and rekey recovery need their own qualification |

The first write scope is a separate same-owner single-user-memory copy only after
storage and namespace gates. Cross-host/principal rebinding requires the separate
attestation/key-custody protocol and tests. Recovery retains source and published
destination evidence, refuses conflicts and needs a fresh preview for staging
cleanup. No new accepted risk exception or privacy waiver is introduced.

## Inert wire boundary controls

The [codec slice](IDENTITY_WIRE_CODEC_WORK_NOTE.md) implements the proposed
standalone wire boundary with a preparse byte limit, exact tags/member sets,
duplicate-key rejection at every object depth, strict integers, full-width
lowercase hex and exact canonical UTF-8 comparison. Invalid representations and
unknown/new outer versions do not fall back to legacy ownership. Diagnostics omit
input identifiers; immutable metadata hides payloads in reprs. Clean-process tests
trap OS queries, directory creation, socket creation and native DLL loading.

Frozen synthetic legacy fixtures retain exact bytes/digests, null/default and
omitted-field behavior, directory ID width and OAuth's separate encoder. These
controls do not authenticate namespace metadata or make decoded file observations
fresh. No existing storage/credential/consumer code adopts the new module.
Accountable review remains open before migration or native admission.
