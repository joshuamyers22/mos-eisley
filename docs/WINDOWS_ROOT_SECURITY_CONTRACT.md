# Bounded Windows directory owner and DACL inspection

Status: preparation and pure parser implemented; native inspection and accountable
prerequisite review pending. Owner: Josh Myers. Date: 2026-10-04. Baseline: `c42eec8`.
Requirement: [plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support)
and [namespace/storage contract](NAMESPACE_STORAGE_CONTRACT.md), N-04/05/06/07/08/09/15.

The smallest first Windows root-admission batch is a **query-only inspector of an
already-open directory HANDLE**, with a pure bounded owner/DACL decoder. Its result
is advisory metadata. It does not return an owned lease, open a pathname or child,
read a namespace record, select an anchor, enroll storage or authorize effects.
Owned root leases and relative child reads follow in separate qualified batches.

This document freezes proposed implementation/acceptance choices, not Windows
support or storage admission. Identity prerequisites require accountable review
before native inspector implementation. Pure parser work can proceed independently.
Public storage/identity selectors, enrollment, existing consumers and writers stay
gated. The [pure parser](../src/mos_eisley/platform/windows_security.py) and
[synthetic fixtures](../tests/test_platform_windows_security.py) now implement
WS-01/02; [verification](WINDOWS_SECURITY_PARSER_WORK_NOTE.md) records portable
source/wheel evidence. No native inspection or root admission is implemented.

## Source boundaries and implementation order

The [principal candidate](../src/mos_eisley/platform/windows_identity.py) queries
fresh TokenUser and refuses thread impersonation. The
[file candidate](../src/mos_eisley/platform/windows_file_identity.py) supplies full
volume/file identity and a local-NTFS device policy; its `standard()` validates
boolean representation but does **not** require a directory, reject delete-pending
state or inspect reparse attributes. Identity equality does not establish privacy.

Implement in this order:

1. Pure self-relative owner/DACL parser and synthetic bounded fixtures; no native
   loading, filesystem operations or authority values.
2. After identity prerequisite review and the cleanup condition below: direct
   Windows query candidate, fixed ABI queries, real source/wheel fixtures and
   independent SDK oracle. Keep the public selector refusing.
3. Separately implement owned directory admission: explicit-rights duplication,
   repeated borrowed/owned observations, non-inheritance and bounded lease cleanup.
4. Separately implement secure relative namespace-child opening/reading, reparse
   and entry binding, followed by anchor/custody and write prerequisites.

Proposed APIs, not current exports:

```text
decode_private_directory_security(payload: bytes, expected: WindowsPrincipal)
    -> WindowsPrivateDacl
inspect_directory_security(opened: WindowsHandle, expected: WindowsPrincipal)
    -> WindowsDirectorySecurityObservation
```

The pure result holds full owner SID and a fixed policy ID. The live observation
adds full root identity, normalized security policy, granted access and selected
directory metadata. Both are immutable, hide private values in reprs, contain no
live HANDLE/native pointer and grant no lease/enrollment/apply authority. A copied
or manually constructed value never substitutes for live qualification.

## Caller reference and native queries

Require exact typed `WindowsHandle`/`WindowsPrincipal` inputs and the existing
AMD64, 64-bit CPython 3.12+, Windows build 17763+ candidate guard before system DLL
loading. No architecture widening or environment/display-name fallback. The caller
keeps the borrowed reference live and prevents close/reuse until inspection ends.
Never close, duplicate, reposition, wait on or change inheritance of that reference.

Request only `OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION` (`0x5`).
Use **GetKernelObjectSecurity** with caller-owned storage. It returns a relative
descriptor and requires `READ_CONTROL`; no SACL request, privilege adjustment,
impersonation change, allocator-returning GetSecurityInfo, LocalFree, pathname
fallback or ACL repair is allowed. This is a project allocation policy, not a
claim that Microsoft's other APIs are unsafe.
[API and rights](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getkernelobjectsecurity).

| Query | Fixed output/call policy |
|---|---|
| Owner/DACL descriptor | One preallocated **65,536-byte** buffer; one native call per observation, **two observations total** per inspection |
| Granted access | `NtQueryObject(ObjectBasicInformation)`, one **56-byte** public structure per observation; no object-name/type query or resize |
| Directory type/lifecycle | `FileStandardInfo`, **24 bytes**; require `Directory=1`, `DeletePending=0`, representable booleans and nonzero link count; directory link count need not equal one |
| Reparse/type attributes | `FileAttributeTagInfo`, **8 bytes**; require directory bit, no reparse-point bit and zero tag; errors and unknown attribute bits refuse |
| Stability metadata | `FileBasicInfo`, **40 bytes**; freeze creation/write/change times and attributes; exclude last-access time from equality |
| Identity/device policy | Reuse reviewed full FileIdInfo and local-NTFS device eligibility; preserve its fixed buffers and pending-output quarantine, without broader filesystem/device exceptions |

For the attribute policy, allow only READONLY `0x1`, HIDDEN `0x2`, SYSTEM `0x4`,
DIRECTORY `0x10`, ARCHIVE `0x20`, NOT_CONTENT_INDEXED `0x2000`, ENCRYPTED `0x4000`.
Require DIRECTORY. Refuse every other bit, including reparse, sparse, compressed,
offline/recall and unknown flags; this intentionally narrow candidate needs real
fixtures before admission. Attribute-tag and basic-info attributes must agree.
Native SDK sizes, offsets and flags must match the independent compiled oracle.
[Attribute constants](https://learn.microsoft.com/en-us/windows/win32/fileio/file-attribute-constants),
[tag information](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_attribute_tag_info),
[standard information](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_standard_info),
[basic information](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_basic_info).

On successful security retrieval require returned length **20–65,536**, within
allocated storage, before inspecting bytes. On failure refuse without parsing any
output; insufficient-buffer/oversized length never triggers allocation growth,
truncation or another attempt. Success with an impossible length also refuses.
Reuse the one security buffer sequentially and release it only after synchronous
completion; copy only bounded normalized values. No returned pointer survives the
call. Fixed native queries accept only documented final success and correct output
lengths where supplied. Unexpected pending completion refuses and retains affected
outputs under a bounded disable-on-uncertainty policy, never frees pending storage.

## Frozen descriptor and DACL profile

This initial **windows-private-directory-owner-dacl-v1** profile is deliberately
narrower than all legal Windows descriptor encodings. The pure decoder accepts
exact `bytes` of 20–65,536 bytes and a typed expected principal, with no native
validation calls on unchecked pointers.

1. Parse the **20-byte self-relative header**, revision 1, reserved byte zero.
   Require SELF_RELATIVE, DACL_PRESENT and DACL_PROTECTED. Accept control exactly
   **`0x9004` or `0x9404`**; the latter also records SE_DACL_AUTO_INHERITED.
   That bookkeeping bit never permits an inherited/inheritable ACE or unprotected
   DACL. Preserve it for freshness comparison. Refuse defaulted owner/DACL,
   auto-inherit-request, absolute descriptors and all other control bits.
   Group/SACL offsets must be zero for
   this owner/DACL-only profile. Native retrieval outside this profile requires a
   separately reviewed policy revision; do not normalize flags or silently broaden
   support. This additional encoding restriction is a project proposal, not an
   assertion that other Windows descriptors are invalid.
2. Owner and DACL offsets must be nonzero, DWORD-aligned, beyond the header and
   bounded by returned length. Validate all extents before slicing. Owner and DACL
   extents cannot overlap. Component order is unrestricted; offsets, not an assumed
   packing order, select components. Do not dereference absolute/native pointers.
3. Owner SID: revision 1, at most 15 subauthorities; exact extent `8 + 4*n`, at most
   **68 bytes**. Compare complete binary SID to the fresh expected/current SID;
   no RID-only, account-name or group-membership comparison.
4. DACL: non-null, ACL revision **2**, zero header reserved fields, bounded
   DWORD-aligned `AclSize >= 8`, and **AceCount exactly 1**. Revision 4/object-specific forms,
   absent/null/empty lists and extra entries refuse.
5. Its sole ACE must be `ACCESS_ALLOWED_ACE_TYPE=0`, **AceFlags=0**, exact
   **Mask=`FILE_ALL_ACCESS=0x001F01FF`**, and the complete current owner's SID.
   `AceSize` must equal `8 + SID length` and fit the ACL. Refuse deny, inherited,
   inheritable, audit, callback, conditional/object ACEs, foreign trustees, generic
   masks, partial masks, trailing application data and unknown types/flags.
6. ACL allocation slack/padding may exist within validated `AclSize`; it grants
   nothing and is not interpreted as another ACE. Compare normalized owner/control/
   ACL revision/type/flags/mask/SID fields across observations, not buffer addresses,
   component order or unused padding. Return neither raw security bytes nor SDDL.

Returned defaulted flags cannot establish how an object was originally provisioned:
Windows does not persist DACL_DEFAULTED as historical creation evidence. Even this
exact private profile proves neither enrollment nor protected anchor custody.
[Control semantics](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control),
[relative descriptor layout](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-dtyp/7d4dac05-9cef-4563-a058-f108abecce1d),
[SID layout](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-sid),
[ACL layout](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-acl),
[allow ACE layout](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-access_allowed_ace).

## Access rights and future owned-reference cleanup

Default query-reference access is **`0x00120080`**: READ_CONTROL,
FILE_READ_ATTRIBUTES and SYNCHRONIZE. Optional directory list/traverse rights may
be present, but granted access must contain all required query bits and be a subset
of the frozen future directory-lease mask **`0x001200A1`**. Write/delete/ownership/
ACL-changing, generic/MAXIMUM_ALLOWED and other rights refuse. No read-directory
enumeration is performed in this slice. Borrowed inheritance may be set; it is
observed and preserved, not repaired or promoted to an owned lease.
[File rights](https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants),
[granted-access query](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntqueryobject).

The future owned lease must check source granted access before requesting exactly
`0x001200A1`; all requested bits must already be granted. Use same-process
DuplicateHandle with `bInheritHandle=FALSE`, `dwOptions=0`, never SAME_ACCESS or
CLOSE_SOURCE. Independently query the duplicate: exact requested access, no inherited
flag, same full identity and unchanged eligible owner/protection. The DACL's owner
full-control mask does not grant the inspector or lease write rights.
Microsoft documents that duplication can change access; specifying a requested mask
alone is not proof of non-broadening.
[DuplicateHandle](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-duplicatehandle).

Later lease acquisition owns cleanup of every partial duplicate, with at most 64
owned/uncertain references, idempotent close, closed-reference refusal before native
queries and no GC cleanup promise. Failed close refuses success, retains bounded
uncertainty, disables acquisition until process reset and is never retried against
a possibly reused HANDLE. These lease mechanisms are not part of the first query
implementation batch.

**Identity cleanup prerequisite:** current `windows_identity._query_principal()`
attempts token close in `finally`, and `NativeTokenApi.close()` raises on failure;
the current source has no retained uncertain-token/acquisition-disable state.
Existing tests prove refusal/close attempts, not bounded repeated acquisition after
unconfirmed close. Accountable identity review must resolve this before the native
inspector claims bounded owned cleanup. Require a process-wide stop after token
release uncertainty, bounded retained token ownership, no close retry, and tests
that later principal/security acquisition cannot accumulate leaked references.
This preparation identifies the condition; it does not implement or approve a fix.

## Fresh inspection and failure policy

Serialize inspector-owned state. Check candidate host/input, then fresh principal
with impersonation refusal and equality to expected. Observe the borrowed handle's
rights, full eligible file identity, directory/tag/basic state and owner/DACL.
Repeat those observations, then query principal again. Require selected fields and
normalized security to agree; failures never return partial observations.

There are exactly two security calls, no convergence loop or background work.
Principal/device helpers retain their separately bounded query budgets; the
64 KiB/two-call descriptor limit does not claim to bound those helpers' total
allocations or calls. No caller-supplied pathname establishes local storage,
reparse absence, selected-root attachment or protected enrollment. Metadata equality
is advisory and cannot prevent all concurrent same-owner changes or establish an
atomic transaction. Kernel/admin/fully trusted process compromise is excluded.

Proposed refusals distinguish unsupported target, unsupported principal context,
native-query/buffer/format failure, object/rights/protection refusal, changed
observation and uncertain release. No absent-data success, fallback, private SID,
raw descriptor, HANDLE value or pathname appears in routine messages/reprs.

## Native source and installed-wheel acceptance

WS-01/02 have portable synthetic implementation evidence in the
[parser note](WINDOWS_SECURITY_PARSER_WORK_NOTE.md). Remaining rows are native
implementation requirements, **not executed native tests or qualification**.

| ID | Required acceptance evidence |
|---|---|
| WS-01 | Pure parser/import traps on every host: no DLL/token/file/clock/randomness access; exact types, bounded input, hidden reprs and no authority promotion |
| WS-02 | Descriptor table: every truncated header/offset/SID/ACL/ACE extent, overlap/misalignment, impossible size/count, unknown revision/control/type/flag, foreign SID and wrong/generic mask refuses; valid components in either order and bounded padding succeed |
| WS-03 | FFI faults: caller buffer cap, 20/65,536 boundary lengths, 65,537 refusal, failed/insufficient-buffer/impossible-success result, exactly two successful calls maximum, no grow/allocator API and no pointer escape |
| WS-04 | Actual native private NTFS directory created by fixture with explicit protected owner-only DACL; independent SDK API oracle agrees on owner, control, ACE, granted access, full identity and all structure sizes/offsets/constants |
| WS-05 | Actual native absent/null/empty/unprotected/additional-ACE/foreign-trustee/inherited/inheritable/partial/generic-mask DACL fixtures refuse; malformed/unknown binary cases remain portable fault evidence, never presented as native OS-created objects |
| WS-06 | Actual borrowed HANDLE survives positive/negative inspection with access, inheritance and position unchanged; invalid/closed handle and missing READ_CONTROL/attributes or excessive rights refuse; fixture closes only its owned handles |
| WS-07 | Actual local-NTFS directory vs regular file, pipe, junction/symlink opened as reparse object and delete-pending directory refusal; portable faults cover unsupported device/filesystem classes; remote/removable/virtual examples require separate owner-operated target evidence |
| WS-08 | Inject principal/impersonation, owner/DACL, rights, identity, type/tag and selected metadata changes between observations; refuse without retry. Native fixture mutates DACL via a separately owned test handle, never through the inspector |
| WS-09 | Token acquisition/query/cleanup faults, native binding failure and pending-device output retention remain bounded; unconfirmed release refuses success and prevents further acquisition without a second native close |
| WS-10 | Native source and dependency-free installed-wheel suites run identical named candidate cases with no silent native fixture/compiler/NTFS skips; portable suite on macOS/Linux exercises parser/FFI/inert public refusal only |
| WS-11 | Root/record public selectors remain refusing on Windows; legacy byte/reader/consumer contracts, POSIX root/read tests, Ruff/Pyright/build/export and full combined make check pass before publication |

Fixture provisioning may set owner/DACL only inside synthetic disposable roots; it
is test setup, not a production enrollment or repair API. No host private stores or
sampling artifacts. Native workers need finite subprocess timeouts and owned-fixture
cleanup. If privilege requirements prevent a real negative fixture, record the
exact gap; do not relabel a mocked case or a skip as native acceptance.

Extend required `windows-files` source and the native-required
`tools/smoke_platform_files.py --require-native-windows` wheel selections, copying the SDK C oracle into the fresh
wheel test root. Required CI fails if the compiler or positive NTFS fixture is
unavailable. Record exact Windows build/architecture/Python/filesystem and named
passes/skips. Ordinary green Windows CI is candidate evidence; accountable review
and explicit admission precede public activation. No CI/runtime changes are made
by the original definition. The pure-parser batch adds portable source and wheel
CI selections without enabling native queries or public selectors.
