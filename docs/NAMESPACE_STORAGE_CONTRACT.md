# Namespace-record and read-only storage-admission contract

Status: proposed storage/enrollment definition; pure record codec implemented, 2026-10-04. Owner: Josh Myers. Baseline: `4d0dd7a`.
Requirement: [plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support).
This freezes the smallest prerequisite to the
[migration design](IDENTITY_MIGRATION_DESIGN.md): one immutable namespace record,
inspection of an existing private directory, and one bounded relative record read.
The [pure record codec](../src/mos_eisley/platform/identity_wire.py) and
[golden fixtures](../tests/test_platform_identity_wire.py) are implemented additively;
[verification](NAMESPACE_RECORD_CODEC_WORK_NOTE.md) covers that slice. Storage and
enrollment APIs remain proposed. A direct
[POSIX root candidate](POSIX_ROOT_ADMISSION_WORK_NOTE.md) now implements existing-root
inspection and owned leases; public storage admission stays closed.
[POSIX fixed-child reading](POSIX_NAMESPACE_READ_WORK_NOTE.md) is also implemented
as a direct candidate, with native macOS source/wheel and portable refusal tests.
Public record reading remains closed. Enrollment
writes, existing store adoption,
migration writers and public Windows selectors remain gated.

## Observed boundaries and chosen scope

The [wire codec](../src/mos_eisley/platform/identity_wire.py) supplies strict
principal/file metadata and namespace-ID syntax, not enrollment.
[Conversation storage](../src/mos_eisley/run/conversation_store.py) currently checks
descriptor type, real-UID ownership, group/other mode bits and regular-file link
count, with POSIX locks and flushes. Those checks do not enumerate ACLs or establish
an enrolled namespace. Its normal create path can create directories/lock files,
so it is not the new read-only admission operation.

The [bounded reader](BOUNDED_FILE_READER_CONTRACT.md) permits ancestor symlinks and
hardlinks and checks neither private ownership nor ACLs. The
[SQLite boundary](../src/mos_eisley/run/conversation_sqlite.py) opens its own
descriptors; admitting a namespace root does not secure those opens. These existing
behaviors remain unchanged. New requirements apply only to the proposed boundary.

Choose a caller-supplied, already-open directory rather than a pathname API or a
general storage service. The caller must securely select its anchor and keep the
borrowed reference live through duplication; this contract neither admits an
ancestor path nor reconstructs one from an integer handle. The adapter owns a
separate read-only lease after successful admission. Path selection, namespace
creation, key custody, locking and publication are separately qualified prerequisites.

## Exact version-1 namespace record

The proposed immutable `NamespaceRecord` has **exactly five required members**:

| Member | Required value |
|---|---|
| `kind` | Exact string `identity-namespace` |
| `schema_version` | Exact integer 1; boolean, float, missing and unknown versions refuse |
| `namespace_id` | Exactly 32 lowercase hexadecimal characters; explicitly generated 128-bit ID at future enrollment |
| `principal` | Exact POSIX UID or full binary Windows SID wire object from the migration design |
| `migration_verification_key_sha256` | Exactly 64 lowercase hex characters: SHA-256 of the enrolled Ed25519 public key's **32 raw bytes**; not a private key, display name, PEM text or backend credential locator |

The algorithm is fixed by this record version; other algorithms require a new
version. Fingerprint syntax alone cannot validate a key or prove possession.
Canonical UTF-8 uses sorted keys, compact separators and no omitted/defaulted fields,
following the existing wire contract. Limit input to 4,096 bytes before JSON parsing;
reject duplicate keys at every depth, noncanonical encodings, invalid tags and extra
members. Encoder output has the same limit. No fallback to `owner_uid` or a missing
key fingerprint, no hostname/environment-derived ID and no reader-generated values.

Freeze exact golden bytes/digests before implementing the codec. Record decoding
is a pure operation and performs no filesystem, OS identity, clock, randomness,
credential or DLL operation. The namespace record's own SHA-256 covers its exact
canonical bytes; keep it distinct from its public-key fingerprint. It may be
projected to `OwnerBinding` metadata but never to enrollment authority.

The fixed child name is `identity-namespace.v1.json`. It is one trusted component,
not user input. Arbitrary names, separators, dot traversal, absolute/drive-relative
names, alternate data streams and case/normalization aliases are not accepted by
this API. No namespace ID or principal is logged in routine diagnostics/reprs.

## Three trust states

| Result | Established fact | Does not establish |
|---|---|---|
| `NamespaceRecord` | Valid bounded bytes with explicit tags/version | Current owner, private storage, host scope, key custody or enrollment |
| `StorageCheckedNamespace` | Selected record read through an admitted live root; current owner, object eligibility, protection and bytes checked | Key possession, enrolled root binding, provenance, migration or write authority |
| `EnrolledNamespaceContext` | Separately verified protected enrollment binds namespace/principal/key and admitted root in a qualified local context | Cross-host equality, historical authorship, execution permission or durable-write qualification |

Only a future reviewed enrollment controller can mint an enrolled context. It must
verify an independently protected enrollment anchor, current principal, public-key
fingerprint and fresh proof of possession from qualified OS-protected key custody.
That anchor pins the namespace, owner, key fingerprint and root binding; it cannot
be reconstructed from the untrusted namespace JSON. Its storage/key-custody contract
must qualify before any production enrollment operation is enabled.

Matching a decoded principal to the OS, possessing a preview hash, or finding private
file permissions cannot promote a result to enrolled. A copied/restored namespace
record can be syntactically valid and privately stored while lacking that enrollment
context. Relocation, account recreation, changed keys and cloned/unknown contexts
require explicit recovery/reenrollment; readers refuse rather than repair them.
The design does not provide physical-machine attestation or protection from a
malicious kernel/administrator or another fully trusted process of the same owner.

## Proposed narrow read-only API and lifetime

The two record codec functions and direct POSIX root/read candidates are
implemented. Public directory admission/record reading below remain gated APIs;
native Windows storage and enrollment remain proposed:

```text
decode_namespace_record(payload: bytes) -> NamespaceRecord
encode_namespace_record(record: NamespaceRecord) -> bytes
admit_private_directory(opened: PosixDescriptor | WindowsHandle,
                        expected_principal: PrincipalIdentity) -> PrivateDirectoryLease
read_namespace_record(root: PrivateDirectoryLease)
    -> StorageCheckedNamespace | NamespaceMissing
```

Admission queries a fresh current principal, refuses unsupported contexts, and
requires exact equality with `expected_principal`. No impersonation/UID-to-SID
fallback is allowed. Input syntax/platform refusal precedes native loading or
duplication. Candidates for unadmitted platforms stay direct qualification APIs;
public selection must refuse until accountable target evidence admits it.

`PrivateDirectoryLease` is process-local, owned, non-inheritable and context-managed.
It holds a separately owned reference, observed principal, full root identity and
the adapter's qualified protection/filesystem policy. It is not serializable or
constructible by decoding an ID. Duplication must not broaden rights; supplied
references with unsuitable access refuse. The caller's borrowed reference is never
closed, repositioned, reconfigured or made inheritable. The caller prevents concurrent
close/reuse until acquisition ends. Partial acquisition attempts cleanup of every
owned reference. Cleanup failure refuses success and reports unconfirmed release;
it must not claim that a failed native close freed the resource. Retain bounded
uncertain ownership and disable further affected acquisition until process reset,
rather than accumulating leaks or blindly retrying a possibly reused handle.
Lease close is idempotent with no second native close; operations after release
refuse before querying or closing a reused reference.

Reading revalidates principal, root identity, protection and eligibility before and
after the bounded operation. It securely opens only the fixed child relative to
the held root. It checks the opened child's actual owner/protection/type, single
link and full identity, and compares the directory entry with that held child before
and after reading. It does not trust a pre-open `stat`, path string or recorded ID.
Changes to selected identity, size, timestamps, protection or publication binding
refuse. Metadata comparisons supplement exact byte hashing; ID equality never
proves unchanged content. A future locked effect boundary must revalidate again;
this observation is not an atomic transaction or a reusable apply authorization.
Replacing a caller's original pathname cannot redirect the held root. Detecting
that pathname's detachment is the separate anchor-selection/enrollment boundary,
not a guarantee derived from root-ID equality in this handle-only reader.

Request/read at most 4,097 bytes total to detect overflow; cap read attempts at 16
and return no truncated record. All per-query ACL/security output buffers are
capped at 64 KiB and native sizing/data attempts at two; unknown/oversized outputs
refuse. An implementation must prove native allocation/lifetime bounds, not merely
check a Python copy after an unbounded allocation. No asynchronous pending buffer
may outlive its allocation. Cleanup failure cannot return successful admission.

`NamespaceMissing` means an admitted root has no selected child at that observation;
it contains no invented owner/namespace and permits no creation. Absent root,
unreadable/unsafe child, malformed record, unknown version, platform/protection/query
failure and selection change are distinct refusals, not missing-data fallbacks.
Errors expose stable categories without private payloads. No mkdir, lock creation,
chmod/chown, ACL repair, write, rename, flush, keychain access or key generation
occurs. Existing files are not opened with write/delete rights or content-changing
flags. Read-access timestamp changes are ordinary OS read effects, not a promise
that all filesystem metadata stays unchanged.

## Admission policy and platform qualification

| Boundary | Required initial policy |
|---|---|
| POSIX context | Qualified macOS/Linux target; fresh real/effective UID equality; expected UID equals OS and object owner |
| POSIX directory | Held directory; exact mode 0700 or 0500, no special mode bits; access ACL absent or base mode-equivalent with no additional principals; default/inheritable ACL absent |
| POSIX record | Held regular file; exactly one link; exact mode 0600 or 0400, no special mode bits; same owner and access-ACL constraints; final child symlink/special-object refusal without blocking |
| Native Windows context | Qualified architecture/build, fresh TokenUser SID and impersonation refusal; expected SID equals OS and security-descriptor owner |
| Native Windows protection | Present non-null, protected, non-defaulted DACL; exactly one explicit non-inherited `ACCESS_ALLOWED_ACE` for the current SID, `AceFlags=0`, `Mask=FILE_ALL_ACCESS`; reject all other trustees/ACE types/flags/masks, including generic-right aliases |
| Native Windows objects | Qualified local-NTFS disk directory/regular record; reject every reparse point, special/remote/removable/virtual/unqualified storage class; full volume/file identity; record link count exactly one |
| All targets | Handle/descriptor-only protection/type/filesystem checks, least read/query rights, bounded queries, no inherited references, fresh observations and owned cleanup |

The Windows DACL grants the owner full control of its protected object; the lease
itself requests only read/query operations. Freeze directory lease access as
`FILE_LIST_DIRECTORY | FILE_TRAVERSE | FILE_READ_ATTRIBUTES | READ_CONTROL |
SYNCHRONIZE`, and child access as `FILE_READ_DATA | FILE_READ_ATTRIBUTES |
READ_CONTROL | SYNCHRONIZE`. No write/delete/ownership/ACL-changing right or generic
mask is requested; duplication must request these explicit rights rather than
same-access duplication. No blanket
Administrators/SYSTEM/Everyone grant is admitted by this initial record policy;
administrator/kernel bypass remains outside its isolation guarantee. Provisioning
that cannot satisfy this deliberately narrow policy must refuse or propose a
separately reviewed policy/version, never silently normalize the DACL.

Do not claim POSIX mode bits establish the entire ACL policy. Linux documents
distinct ACL access checks and default ACLs, and Apple exposes descriptor-based
extended ACL inspection. Query errors/unsupported inspection cannot be interpreted
as absence. [Linux ACL semantics](https://www.man7.org/linux/man-pages/man5/acl.5.html),
[Apple descriptor ACL interface](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man3/acl_get_fd_np.3.html).
Windows documents handle-based owner/DACL retrieval and its `READ_CONTROL`
requirement; that is a query prerequisite, not privacy or allocation qualification.
[Microsoft GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo).

Filesystem identity and privacy do not establish durability. Each admitted target
needs its own exact OS/build/architecture/filesystem and API qualification record.
POSIX eligibility must use an established descriptor-based filesystem/mount policy,
not a hostname, path prefix or environment guess. Native candidate identity tests
and ordinary NTFS CI do not admit ACL, secure relative opens, locks or flushes.
Unknown filesystem/context remains unsupported. No capability is advertised here.

## Enrollment and write prerequisites remain closed

Future explicit enrollment selects an already-qualified root and owner, creates a
fresh namespace and OS-protected Ed25519 key, then publishes the immutable record
with no overwrite and independently registers its protected root/key anchor. It
never adopts a pre-existing foreign/unregistered record automatically. Preview
must freeze selected root/owner/protection, expected absence, record bytes/digest,
key fingerprint and exact qualification-policy version; apply must verify consent
and all live conditions under a qualified lock immediately before effects.

The required state sequence is `prepared -> key_unbound -> record_unregistered ->
enrolled`. Only the last state permits an enrolled context. There is no claimed
atomic transaction spanning key custody and the filesystem. Every interruption
requires explicit bounded recovery of observed record, root and custody state;
uncertain publication/flush/registration stays unregistered. Never delete a
published record or key as an automatic rollback. Changed/conflicting targets
refuse without overwrite; cleanup needs its own fresh preview and owner consent.

Before enabling that writer, qualify secure root selection/child creation, private
mode/DACL at creation, non-inheritance, interprocess lock lifecycle, no-overwrite
publication, file and directory durability, protected custody/anchor persistence,
proof of possession, and crash recovery on each target. Private record inspection
does not satisfy any of these write gates. Enrollment grants neither migration
write authority nor approval to import retained task/review permissions.

## Required acceptance and efficient batches

These are requirements for the complete boundary. The pure codec note records
its limited executable coverage; storage, enrollment and native evidence remain
pending:

| ID | Required evidence |
|---|---|
| N-01 | Exact version-1 record round-trip/golden bytes/digest; SID and public-key fingerprint widths; no missing/default/extra fields, bool/float version aliases or unknown versions |
| N-02 | Preparse 4 KiB bound, nested duplicate/encoding refusal, malformed/principal/hex failures and clean source/wheel inert import with OS/filesystem/custody traps |
| N-03 | Valid/copied private record decodes and can be inspected but cannot mint enrollment; missing anchor, wrong pinned root/key, stale possession proof and cloned/unknown context refuse trust promotion |
| N-04 | Fresh POSIX UID/effective-UID and Windows SID/impersonation checks; changed principal mid-operation refuses; no environment/display-name fallback |
| N-05 | Borrowed root survives success/failure; owned duplicate/child close on every path; non-inheritance, invalid/reused/closed references, duplication and cleanup faults |
| N-06 | Private directory and single-link regular record accepted only under frozen mode/ACL/DACL policy; null/default/inherited/foreign/unknown ACL and query failure refuse |
| N-07 | Symlink/junction/reparse, ADS/name alias, FIFO/pipe/device, multiple links and unsupported filesystem/context refuse; no path-based fallback or blocking read |
| N-08 | Held-root identity/protection change, child replacement/entry detachment and content mutation despite unchanged ID refuse; pathname substitution never redirects the held root, but anchor detachment needs separate validation; observations cannot be reused as apply grants |
| N-09 | Empty/partial/exact-limit/overflow/short-read exhaustion and native query/buffer/pending/cleanup faults remain bounded, with no writes or payload logging |
| N-10 | Missing child returns typed absence without creating root/record/lock/key; malformed/inaccessible/unsafe child never becomes missing or triggers repair |
| N-11 | Enrollment refuses existing/conflicting records, changed previews and failed custody proof; no-write qualification returns no write capability |
| N-12 | Inject every key/publication/flush/anchor interruption; only fully confirmed enrollment mints context; uncertain state, exact retry and explicit recovery preserve evidence |
| N-13 | No secret/private-key material in records/logs/previews; registered public fingerprint verifies exact raw-key bytes and qualified protected custody |
| N-14 | Original legacy schemas/bytes/hashes and current reader/writer/selector behavior stay unchanged through every additive batch |
| N-15 | Real target positive/negative ACL, relative-open and lifecycle tests from source and fresh wheels; mocks supplement, unavailable fixtures leave admission pending |
| N-16 | Lock/no-overwrite/durability/custody/recovery qualification and accountable review precede any writer or public Windows selector activation |

Implement in this order, with independent qualification records:

1. **Pure namespace record codec and golden fixtures — implemented additively**
   (N-01/02/03 metadata-only/14). The [codec note](NAMESPACE_RECORD_CODEC_WORK_NOTE.md)
   records source/wheel evidence. No enrollment context, platform loading or storage
   operation; protected-anchor/custody evidence under N-03 remains pending.
2. **POSIX existing-root read-only admission — direct candidate implemented**,
   frozen ACL/mount policy and owned reference lifecycle (N-04/05/06/15).
   [Evidence](POSIX_ROOT_ADMISSION_WORK_NOTE.md) covers native macOS source/wheel
   and portable faults; exact target qualification and accountable admission remain pending.
   No existing store adoption or creation; public storage selection stays closed.
3. **Secure fixed-child namespace reads**, bounded bytes and replacement/refusal
   tests (N-07/08/09/10/14/15) — direct POSIX candidate implemented. The
   [reader note](POSIX_NAMESPACE_READ_WORK_NOTE.md) records real native macOS
   source/wheel checks, descriptor ACL/entry/content checks and owned child cleanup.
   Exact Linux reader qualification and accountable target admission remain pending. Keep
   storage-checked observations advisory and public selectors closed.
4. **Native Windows admission/read candidates** after prerequisite identity review;
   verify the frozen masks and qualify DACL/reparse/relative-open/local-NTFS cases on
   actual targets. The [smallest Windows query batch](WINDOWS_ROOT_SECURITY_CONTRACT.md)
   is now defined: bounded owner/DACL inspection of a borrowed directory HANDLE,
   with the [pure parser and synthetic fixtures](WINDOWS_SECURITY_PARSER_WORK_NOTE.md)
   implemented additively; native queries, owned root leases and child reads remain
   subsequent batches. Its token-release uncertainty
   prerequisite must be resolved before native implementation. Public selectors
   remain closed until N-15/16 admission.
5. **Protected custody/anchor plus locking/publication/durability contracts and
   fault suites** (N-11/12/13/16); then separately authorize explicit enrollment.
6. **Same-owner memory preview/copy** only with confirmed enrollment and independently
   admitted write storage; retain all migration/review/legacy authority gates.

Definition verification and remaining work are recorded in the
[work note](NAMESPACE_STORAGE_CONTRACT_WORK_NOTE.md). This contract completes the
preparation slice; it does not complete enrollment, storage implementation or native
release qualification.
