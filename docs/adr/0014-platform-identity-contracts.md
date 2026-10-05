# ADR-0014: Separate principal and opened-file identity from storage policy

- Status: proposed; implementation and accountable boundary review pending
- Date and owner: 2026-10-03, Josh Myers
- Requirement: [plan §27.2](../mos-eisley-plan.md#272-version-011--full-native-windows-support)

## Context and options

Current conversation/memory/guidance artifacts retain integer `owner_uid` values;
private stores compare those against `os.getuid()` alongside permissions, object
type, link counts, locks and hashes. Device/inode observations also occur in root,
lock, directory selection and migration preview checks. Windows needs SID and
full-width volume/file-ID representations without interpreting a SID as a UID or
claiming that identifier equality alone enforces private storage.

Keeping direct POSIX calls leaves that dependency unresolved. A universal service
object or optional-field UID/SID record adds unrelated responsibilities and permits
ambiguous states. A schema-wide replacement now would mix platform extraction with
retained-byte/hash migration and owner-rebinding policy.

## Decision and consequences

Define immutable, tagged principal and file-identity unions with narrow lazy query
functions and distinct borrowed POSIX descriptor/Windows HANDLE inputs. Pure values
carry identifiers only. Current-principal semantics retain the real UID on POSIX,
with explicit refusal for unequal real/effective UIDs in the new API. The initial
Windows owner context uses the process TokenUser SID and refuses impersonation;
full token privilege/access policy remains separate. File queries inspect already
opened objects and preserve full identity width without opening a path.

The [contract specification](../PLATFORM_IDENTITY_CONTRACTS.md) is normative for the
proposed API, comparison preconditions, failures and acceptance matrix. Identifier
comparison requires established common host/namespace and fresh live references;
values do not establish that scope themselves. They do not authenticate retained
artifacts, secure SQLite's separately opened descriptors or replace privacy checks.

Deliver pure values plus POSIX queries and explicit Windows refusal first. Qualify
native read-only identity adapters on real Windows/local NTFS in a separate batch.
Keep every consumer and persisted schema unchanged until a later explicit migration
contract versions host/account binding and preserves original bytes/hashes.
No new dependencies, credential changes, process authority or storage writes are
required for this definition or the initial additive implementation.

Costs: callers still perform their existing checks until adoption; correct native
FFI lifetime/bounds, context admission and filesystem eligibility need dedicated
fault and host tests. Real/effective UID mismatch and impersonation refusal are
intentional new-API limits, not claims that all existing callers enforce them.
Removing additive modules before adoption is a rollback without data conversion.
After adoption, recovery must follow the separately versioned migration policy.

## Verification

The specification defines I-01–I-09: strict tagged values, inert import/refusal,
real POSIX principal/descriptor queries, lifetime/rename/hardlink/replacement tests,
native token and full-width handle identity, fault/cleanup tests, source/wheel
packaging and exact legacy bytes/hashes. Native mocks supplement native execution.
Unavailable privilege/filesystem cases leave their qualification gates open.

This ADR is a design definition, not implementation evidence or release approval.
Reconsider if safe scope binding cannot be established, required targets lack the
full identity API, native context cannot be admitted, or consumer adoption requires
changing retained evidence before migration acceptance is frozen.

## Additive implementation status

The [POSIX slice](../PLATFORM_IDENTITY_IMPLEMENTATION_WORK_NOTE.md) implements the
pure tagged values, borrowed references and lazy POSIX queries, with explicit
native refusal. Existing consumers and schemas remain unchanged. The ADR remains
proposed for native admission and later adoption; this local implementation does
not stand in for accountable native qualification or migration approval.

The [candidate Windows principal slice](../WINDOWS_PRINCIPAL_WORK_NOTE.md) adds
direct process TokenUser acquisition and qualification tests. The common Windows
selector remains closed until actual native evidence and accountable admission.
Native file identity and consumer/schema adoption remain open.
