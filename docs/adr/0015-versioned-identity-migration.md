# ADR-0015: Preserve legacy identity evidence and migrate through new versions

- Status: proposed; accountable design review and implementation pending
- Date and owner: 2026-10-03, Josh Myers
- Requirement: [plan §27.2](../mos-eisley-plan.md#272-version-011--full-native-windows-support)

## Context and options

[ADR-0014](0014-platform-identity-contracts.md) separates queried principal/file
values from storage policy. The [source inventory](../IDENTITY_MIGRATION_INVENTORY.md)
finds integer owners in durable and nested records, device/inode directory bindings,
hash-bound maintenance previews, SQLite metadata/indexes and implicit OAuth key
bindings. Replacing leaf fields in place would change canonical hashes, leave
enclosing versions ambiguous and risk transferring authority across owners.

Alternatives are automatic on-read conversion, a global UID-to-SID mapping, or
side-by-side explicit versioned conversion. The first two cannot preserve the
original interpretation or authenticate destination ownership.

## Decision and consequences

Propose the [migration design](../IDENTITY_MIGRATION_DESIGN.md): strict tagged wire
forms, enrolled owner namespaces, separate legacy/new decoders, retained original
bytes and explicit source-to-destination provenance. Allocate versions by artifact
family and dependency closure; invalidate destination previews/cursors and rebuild
derived indexes. Original evidence never becomes destination execution permission.

Begin with inert codecs and compatibility fixtures, then qualified storage and
namespace enrollment, a read-only single-user-memory preview and same-owner copy
with bounded crash recovery. Defer graphs/SQLite, authenticated cross-namespace
rebinding and credential migration to separately reviewed slices. Rebinding needs
role-enrolled source/destination attestations; metadata equality or a preview hash
alone is insufficient. General artifact migration never copies OAuth secrets.

Costs are dual decoders, explicit destination storage, new digests/reference graphs
and preserved historical artifacts. This avoids silent mutation and permits rollback
to the untouched source. New destination activity cannot be discarded by downgrade.
Native identity qualification does not qualify DACLs, locks or durable publication.

## Verification and reconsideration

The design specifies M-01–M-16 and ordered implementation gates. The
[work note](../IDENTITY_MIGRATION_WORK_NOTE.md) distinguishes existing compatibility
regressions from future acceptance. This ADR grants no native admission or writer
approval. Reconsider if namespace/key custody cannot establish the intended scope,
qualified storage cannot publish/recover safely, or a family cannot retain its
original evidence and refuse transferred authority.

## Additive codec implementation

The [inert codec slice](../IDENTITY_WIRE_CODEC_WORK_NOTE.md) now implements the
standalone pure wire forms and selected synthetic legacy fixtures. It does not
enroll namespaces, change retained records, admit native selectors or implement
rebinding/storage authority. The ADR remains proposed for accountable design review
and subsequent adoption.
