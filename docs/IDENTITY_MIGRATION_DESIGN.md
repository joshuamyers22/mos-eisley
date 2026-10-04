# Versioned principal and file-identity migration design

Status: proposed design, 2026-10-03. Owner: Josh Myers. Source baseline: `f638e6b`.
Requirement: [plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support).
The [inventory](IDENTITY_MIGRATION_INVENTORY.md) records observed schemas; this
document specifies intended behavior. The initial documentation batch defined this boundary. The additive
[inert codec slice](IDENTITY_WIRE_CODEC_WORK_NOTE.md) now implements standalone
wire forms and selected legacy fixtures; no migration command, writer or consumer
adoption is implemented. Candidate adapter
PR [#268](https://github.com/joshuamyers22/mos-eisley/pull/268) and native/accountable
qualification remain separate gates.

## Identity wire contract

Use strict discriminated objects. Unknown tags, extra fields, boolean/float integer
aliases, missing members and noncanonical hex refuse. Never derive a UID from a
SID/RID, a SID from a username, or a Windows file ID from a path or truncated ID.

| Value | Exact members and constraints |
|---|---|
| POSIX principal | `{"kind":"posix-uid","uid":1000}`; `uid` is a nonnegative JSON integer, validated against the existing pure-value contract |
| Windows principal | `{"kind":"windows-sid","sid_hex":"…"}`; lowercase complete binary SID bytes, 8–68 bytes, revision 1 and exact subauthority count/length, matching the pure SID contract |
| POSIX opened-file identity | `{"kind":"posix-file","device":1,"inode":2}`; both nonnegative JSON integers, retaining every bit |
| Windows opened-file identity | `{"kind":"windows-file","volume_serial_hex":"0000000000000001","file_id_hex":"00000000000000000000000000000002"}`; exactly 16 and 32 lowercase hex characters. Serial is the unsigned 64-bit value rendered most-significant digit first; file ID is the original 16 opaque bytes in native-return order |
| Owner binding | `{"namespace_id":"<32 lowercase hex>","principal":<principal object>}`; exact members, required wherever a new record asserts an owner |
| Scoped file observation | `{"namespace_id":"<32 lowercase hex>","identity":<file object>}`; metadata for a freshly qualified reference, never an access grant |

These forms are new wire types, not automatic JSON serialization of existing
dataclasses. UID/device/inode integers stay exact in the Python decoder; external
readers must use exact integer parsing or refuse values they cannot represent.
Windows fixed-width fields use hex to avoid lossy JSON-number consumers.

New outer records have both a fixed domain `kind` and integer `schema_version`.
Standalone identity/owner-binding decoding is capped at 4,096 UTF-8 bytes before
JSON parsing. Decode bounded UTF-8, reject duplicate object keys before model
validation, enforce per-family byte/item bounds for enclosing artifacts, then
validate all tags and the exact canonical bytes.
Do not widen an old decoder or insert fields into its hash body. New records use
the existing core canonical JSON/SHA-256 rules with explicitly frozen omission
rules. File identity, path, content digest and timestamps remain separate fields.

## Establishing namespace and owner scope

A namespace is an explicitly enrolled local principal-comparison context, not a
machine name, environment variable, SID display name or volume serial. Its protected
version-1 record contains `kind="identity-namespace"`, `schema_version=1`, a random
128-bit `namespace_id`, the enrolled principal and a migration verification-key
fingerprint.
Enrollment is an explicit future operation after storage admission; reads never
create or repair the record. Current OS principal and private namespace storage
must be verified before trusting it. Namespace IDs are metadata, not authentication.

Each host/security namespace enrolls separately. Copied namespace files alone do
not establish trust: migration signing keys require qualified OS-protected custody
and explicit enrollment in the verifier's trust policy. A restored or cloned record
without that established context requires reenrollment and fresh previews. This
does not promise physical-machine attestation or protection from a malicious
administrator. Account deletion/recreation and UID reuse are not solved by equality;
recovery after such changes requires explicit owner verification and reenrollment.

Legacy `owner_uid` records have **no authenticated host namespace**. Preserve that
absence in provenance; do not infer it from the destination. A source-side current
principal observation and admitted source root can establish a selected local
conversion context, not retrospective proof of the historical author's identity.
Different namespaces or principal kinds never compare equal for admission. Even
within a namespace, file identity comparisons require live original references
and fresh content verification; an old inode/file ID is not a permanent identity.

## Version allocation and compatibility

| Family | Proposed new allocation |
|---|---|
| State, memory, guidance snapshot/bindings/pins, requirements, policy, frozen role context, prepared review and assessment families currently at 1 | Version 2, with explicit kind and owner binding; all changed enclosing records get their own new version |
| Task archive bundle supporting 1/2 | Version 3; manifest 2. Inventory each nested task record's highest existing version before reserving its next version; never assume all task records are v1 |
| Author compaction and resume header | Version 2; destination active context is regenerated against new bindings |
| SQLite | `user_version=2` with a distinct exact schema and metadata owner-binding encoding; explicit version-2 index/header forms; create a new store ID |
| Transfer/retention/prune/cleanup and their version-1 batch envelopes | Next version 2, including enclosing receipts; old apply decoders remain bound to old plans |
| Export plan already supporting 1/2 | Version 3; independently version its receipt/batch envelope when nested form changes |
| Unversioned navigation, selection and raw maintenance dictionaries | Explicit new domain kind/version 2; old implicit form remains legacy, not a default for missing version |
| New migration manifest, preview and receipt | New `identity-migration-*` kinds, version 1; distinct from current same-owner JSON-to-SQLite migration |
| MCP credentials/configuration | Separate new OAuth key namespace/binding and versioned HTTP token-owner settings contract; outside the artifact migration command |

These are reserved design choices, not permission to change every writer together.
Freeze exact field sets, bounds and golden fixtures for each slice before code.
Use a separate new-model decoder alongside the unchanged legacy decoder. Initial
legacy POSIX writers remain unchanged until explicit adoption; qualified Windows
writers may emit only the new platform-aware family, never `owner_uid` placeholders.
There is no permissive fallback from malformed/new/unknown versions to legacy.

Legacy bytes, source JSON strings, signatures and hashes are retained exactly.
Keep raw-byte SHA-256 separate from the legacy canonical-object digest; they may
differ. A converted destination has a new canonical digest and records a provenance
edge to the original bytes. Never claim that new bytes retain an old digest or
replace a historical signature with a recomputed one. Unsupported/noncanonical
source records may be preserved as opaque evidence but cannot become active state.

New readers support their explicitly tested legacy/current versions on compatible
owners; incompatible owner/platform records are historical-only or refuse. Old
readers must reject the new kind/version without writing. Downgrade means switching
back to the untouched source store, not stripping tags or rewriting destination
records into v1. Any newer destination activity requires separate reconciliation;
never discard it as part of rollback.

## Conversion authority and retained history

The first writable scope is **one standalone user-memory document, same admitted
local owner and namespace**, to a separate empty destination. No project mapping,
session graph, credential or execution authority is included. Preserve text,
enabled state and source revision in provenance; the destination starts its own
revision lineage at 1. Conversion requires an explicit preview hash and fresh owner,
root, source-byte and destination-absence verification. A hash confirms a selection,
not a foreign owner's consent.

Cross-principal or cross-host conversion stays disabled until a separate
authenticated rebinding implementation qualifies. Its proposed protocol requires
two domain-separated Ed25519 attestations over the same bounded canonical manifest:
`mos-eisley.identity-migration.source.v1` and
`mos-eisley.identity-migration.destination.v1`. An explicitly enrolled source key
attests a live source principal/root and exact selected artifact digests; an
independently enrolled destination key consents to the target owner, namespace,
schema and path/project mapping. Trust configuration binds keys to their roles and
owner namespaces; a self-asserted key or copied namespace record is insufficient.

The manifest includes both owner bindings, source and destination root observations,
sorted artifact IDs and raw/canonical digests, destination schema versions, explicit
mapping, item/byte limits, policy version, random nonce and expiration. Sign the
UTF-8 domain string plus a zero byte plus canonical manifest bytes. Verify both
attestations, expiration and consumed nonce before effects, then revalidate local
effect-boundary observations. Persist nonce consumption with destination publication
so retries cannot create another import; receipt-only recovery is allowed. Source
and destination may be controlled by the same human, but that is not independent
security review. Key custody, enrollment/revocation, bounded verification and durable
nonce handling need dedicated design review/tests before enabling this protocol.

Neither conversion mode transfers approvals, execution/continuation permissions,
locks, cleanup selections, OAuth tokens, spend reservations or retry authority.
Completed history remains verified under original bindings. Active destination
guidance/compaction/task context must be rebuilt and approved through existing
gates. A foreign legacy nested object cannot be inserted as active destination state
by bypassing owner validators; use an explicitly typed historical reference to its
original bytes. Queued/running/uncertain attempts do not resume or retry on import.

## Prepare, publish and recover

1. **Prepare without mutation.** Decode only the selected bounded source family;
   verify byte/canonical hashes, owner context, private roots and the full selected
   dependency closure. Unsupported schema or missing child refuses. Freeze a new
   versioned preview containing owner bindings, live root/file observations, source
   hashes, expected destination absence, target versions and byte/item limits.
2. **Revalidate before effects.** Require explicit expected preview hash, current
   principal and eligible live references. Recheck root admission, selected bytes,
   destination absence and fresh plan equality under the qualified lock protocol.
   Refuse source replacement, content change despite stable ID, foreign namespace,
   changed generation, symlink/reparse ambiguity or insufficient storage policy.
3. **Stage a separate destination.** Use qualified private creation, bounded writes,
   content verification and durability operations. Never hardlink the old payload
   or modify the source. New identity alone does not qualify DACLs, link policy,
   locks, atomic no-overwrite publication, flushes or SQLite's own opens.
4. **Publish with no overwrite.** Single-document migration atomically publishes
   the verified staged record and syncs required directories. Persist provenance and
   publication/nonce state in the qualified commit protocol. For a later graph,
   stage all content-addressed children and publish the generation manifest last;
   readers accept one complete committed generation. A filesystem batch is not
   claimed to be atomically published as one operation.
5. **Recover from observations.** A bounded receipt records source/destination
   hashes, target versions, published prefix or committed generation, source retained
   and durability status. Failure after rename/flush is `durability_unconfirmed`,
   not successful rollback. Fresh recovery verifies exact destination bytes and
   provenance; return an already-published receipt only for the same committed
   manifest. Conflicting/unverifiable targets refuse without overwrite or deletion.
6. **Rollback explicitly.** The original source remains usable. Removing verified
   unpublished staging requires a new bounded cleanup preview. Switching readers
   back to the source requires explicit selection and preserves all destination
   evidence. No recovery routine silently deletes published destination records.

SQLite migration is a later distinct slice: copy verified logical records into a
new exact-schema database under a qualified transaction/storage contract, rebuild
indexes/headers, issue a new store ID and invalidate all old cursors/selections.
Do not `ALTER` an old owner field in place, recover a hot journal as a preview side
effect or claim root-ID comparison secures SQLite's separately opened handles.

OAuth is also separate: freeze the v1 binding encoder and owner checks. A future
platform-aware key namespace must include a versioned owner binding and the exact
resource/issuer/client/account/scope contract. Cross-host migration requires fresh
login; tokens and refresh secrets never enter migration artifacts. Same-host rekey
needs its own authenticated keychain/lock/logout recovery protocol and tests with
fake backends before any real credential change. No destination v1-key fallback.

## Acceptance matrix and efficient implementation order

The matrix defines acceptance for the full migration. The
[inert codec record](IDENTITY_WIRE_CODEC_WORK_NOTE.md) records implemented wire
checks, selected legacy fixtures and legacy/new-version refusal for the first
slice of M-02/03/05/06. Remaining artifact families, migration rollback and all
storage/adoption gates are future acceptance. Earlier existing regression evidence
is recorded in the [design work note](IDENTITY_MIGRATION_WORK_NOTE.md).

| ID | Required positive/negative evidence |
|---|---|
| M-01 | Source-linked dependency closure distinguishes durable records, derived indexes and temporary observations; a newly discovered nested owner blocks its slice |
| M-02 | All four exact wire forms round-trip; full SID and high serial/file-ID bits survive; malformed lengths/tags, uppercase hex, extra/duplicate keys, booleans/floats, oversized data and unknown versions refuse |
| M-03 | Golden legacy canonical bytes, omitted/null fields, exact retained source strings, raw/canonical digests and content-addressed names are unchanged in source and installed wheel |
| M-04 | Same-owner legacy decoding works; foreign owner/namespace and absent/copied/untrusted namespace enrollment refuse without creating storage |
| M-05 | Old readers reject new records; new readers never fall back from invalid new records; rollback retains original and newer destination evidence |
| M-06 | Pure codec import performs no OS query, keychain access, directory creation or native selector admission |
| M-07 | Read-only preview refuses unsupported source/dependency/bounds and wrong owner before destination mutation; deterministic manifest/hash includes every selected dependency |
| M-08 | Same-owner single-memory copy preserves text/enabled/source provenance, starts destination lineage and retains source bytes; an already-published exact retry returns a receipt without another write |
| M-09 | Source content mutation with unchanged file identity, replaced source/root, changed principal and destination appearing during publish all refuse safely |
| M-10 | Inject failure at stage/write/sync/publish/receipt and recovery boundaries; distinguish unpublished, committed and durability-unconfirmed states, never overwrite/delete conflicting published data |
| M-11 | SQLite exact schema/version, nested owner, artifact closure, index/header hashes and new store ID validate; old/foreign/stale cursors refuse; hot journal preview stays inert |
| M-12 | Mapping relocation freshly selects destination roots; absent legacy path remains absent; stale memory/guidance/cleanup/transfer apply hashes cannot act on destination |
| M-13 | Historical signatures, compaction source digests and task/review records remain verifiable; migrated history cannot approve, resume, retry or grant execution |
| M-14 | Rebinding requires enrolled role-bound keys, both exact domain-separated attestations and fresh local observations; changed mapping/owner/hash, missing/expired/revoked signatures, nonce replay and untrusted self-enrollment refuse before effects |
| M-15 | OAuth v1 lookup hashes remain exact; new owner/key namespace cannot retrieve another account's credentials; artifact migration never reads/exports tokens, including on error |
| M-16 | Each admitted platform/storage slice passes source and fresh installed-wheel positive/negative suites on real qualified targets; unavailable native fixtures remain pending |

Implement in this dependency order:

1. **Pure wire codecs and frozen legacy fixtures — implemented additively.**
   The [codec record](IDENTITY_WIRE_CODEC_WORK_NOTE.md) covers new inert
   principal/file/owner-binding contracts, strict decoding and
   selected legacy golden fixtures. No namespace enrollment, writers or consumers;
   M-02/03/05/06. Can proceed while adapter CI/review runs.
2. **Namespace enrollment and storage prerequisites.** Qualify principal/file
   selectors through accountable review, then protected namespace records, private
   create/open/lock/durability APIs. M-04/09/10/16; native Windows storage remains
   blocked until its separate contracts pass.
3. **Single-document same-owner preview.** Freeze the user-memory v2 and migration
   manifest/receipt fields, bounds and read-only preview. M-01/07 plus codec gates.
4. **Single-document copy and recovery.** Implement the first bounded write scope
   above; M-08/09/10/16 and accountable boundary review before adoption. No
   cross-owner import in this batch.
5. **Memory mapping and guidance graph, then sessions/tasks/SQLite.** Work by closed
   dependency family, allocate outer versions, rebuild derived state and invalidate
   previews. M-01/03/05/11/12/13/16, full implementation gates per published slice.
6. **Authenticated cross-namespace rebinding and separate credential work.** Only
   after their trust/key custody/recovery designs and reviews pass; M-14/15/16.

Accountable design review, remaining per-slice schemas/acceptance tests, native
admission and all runtime adoption remain open. These gates do not prevent completing and
reviewing this inventory/design now.
