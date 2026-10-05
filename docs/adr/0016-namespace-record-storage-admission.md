# ADR-0016: Separate namespace metadata, storage inspection and enrollment

- Status: proposed; pure record codec and POSIX root/read candidates implemented; accountable admission, native Windows storage and enrollment pending
- Date and owner: 2026-10-04, Josh Myers
- Requirement: [plan §27.2](../mos-eisley-plan.md#272-version-011--full-native-windows-support)

## Context and options

[ADR-0015](0015-versioned-identity-migration.md) needs an explicitly enrolled
namespace before conversion. Pure owner bindings and existing owner/mode/link checks
do not establish protected key custody or enrollment; some storage constructors
also create directories and locks. Automatic enrollment during reads would turn
untrusted retained metadata into local authority and introduce hidden writes.

Options are a general storage manager with automatic setup, a keyless namespace
that must be replaced later, or a small immutable record and separate read-only
admission with enrollment kept behind explicit prerequisites.

## Decision and consequences

Choose the [namespace/storage contract](../NAMESPACE_STORAGE_CONTRACT.md): one exact
versioned bounded record, existing-root admission and a fixed relative child read.
Distinguish decoded metadata, storage-checked observation and a separately verified
enrolled context. Freeze a required raw Ed25519 public-key fingerprint; decoding
never creates a key or infers its custody. Unknown protection/context refuses.

Require descriptor/handle privacy and ACL checks, owned non-inheritable references,
bounded read/query cleanup and fresh entry/content observations. Do not adopt this
boundary into existing stores or open public Windows selection. POSIX/Windows
platform details need their own exact qualification policy and native evidence.

Costs are additional ACL/custody qualification and explicit recovery across the
record/key/anchor publication states. The deliberately narrow initial protection
policy may refuse otherwise usable stores. Broader policies need separate review.
Before adoption, rollback removes only additive definitions/implementations; after
enrollment, recovery preserves records and keys rather than silently undoing them.

## Verification

The contract specifies N-01–N-16 and efficient independent slices, beginning with
pure record codecs and fixtures. The [work note](../NAMESPACE_STORAGE_CONTRACT_WORK_NOTE.md)
records definition evidence and limitations. The subsequent
[pure codec slice](../NAMESPACE_RECORD_CODEC_WORK_NOTE.md) adds namespace metadata
and golden fixtures only. A subsequent
[POSIX root candidate](../POSIX_ROOT_ADMISSION_WORK_NOTE.md) implements bounded
read-only root inspection and owned leases, with native macOS evidence and public
selection still closed. The
[fixed-child POSIX reader candidate](../POSIX_NAMESPACE_READ_WORK_NOTE.md) adds
bounded relative record inspection, real descriptor ACL/entry checks and owned
child cleanup, with native macOS source/wheel evidence. Exact Linux reader qualification,
native Windows storage, production writers, key provisioning and accountable
target admission remain pending.
The [Windows root security preparation](../WINDOWS_ROOT_SECURITY_CONTRACT.md)
selects caller-buffer owner/DACL queries and a pure bounded decoder as the first
Windows slice. Borrowed inspection precedes independently qualified owned leases
and relative reads; token-release uncertainty remains an identity prerequisite.
The [pure parser](../WINDOWS_SECURITY_PARSER_WORK_NOTE.md) is implemented with
synthetic fixtures; no native inspection or admitted adapter is claimed. Reconsider if ACL
inspection/allocation bounds cannot qualify, root/key enrollment cannot be pinned
without circular trust, or publication recovery cannot retain uncertainty safely.
