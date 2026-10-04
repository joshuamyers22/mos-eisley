# Persisted identity migration inventory

Observed at `f638e6b` for [plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support).
This is a source inventory, not an inspection of private stores. The candidate
adapters have not changed these representations. The accompanying
[design](IDENTITY_MIGRATION_DESIGN.md) proposes their eventual treatment.

## Durable records and indirect dependencies

An identity-bearing leaf is only part of the migration. Every containing record,
content-addressed filename, reference and validator belongs to its dependency
closure. Existing versions below describe current source, not new implemented
schemas. A slash in the version column means multiple currently supported versions.

| Family and source | Existing identity or dependency | Current version; treatment |
|---|---|---|
| [Conversation state](../src/mos_eisley/conversation_state.py), [JSON snapshots](../src/mos_eisley/run/conversation_store.py) | `ConversationState.owner_uid`; embedded memory, guidance, task scope and compaction; snapshot hash covers the state | State 1; new state and wrapper decoding must preserve the original snapshot and all nested hashes |
| [Memory documents](../src/mos_eisley/conversation_memory.py) | `MemoryDocument.owner_uid`; user/project scope, workspace and `MemorySnapshot` canonical hash | Document 1; begin with a standalone user document before project or session graphs |
| [Saved memory mappings](../src/mos_eisley/conversation_memory_registry.py) | Registry `owner_uid`; `MappedDirectory.path/device/inode` in both workspace and target; backup names hash raw registry bytes | Registry 1; old directory identities remain provenance, destination mappings require fresh selections |
| [Mapping import manifest](../src/mos_eisley/conversation_memory_registry_import.py) | Manifest `owner_uid`; proposed paths inspected before applying | Manifest 1; invalidate old previews rather than accepting them under a new owner |
| [Guidance snapshots](../src/mos_eisley/project_guidance.py) | `owner_uid`, workspace, exact descriptor JSON and markdown, descriptor and snapshot hashes | Snapshot 1; preserve exact retained source strings, independently version a destination snapshot |
| [Guidance bindings](../src/mos_eisley/project_guidance_binding.py) | Binding `owner_uid`, mapped workspace; `PinnedGuidance` embeds a mapped workspace and snapshot; snapshot filenames use digests | Bindings and pins 1; migrate the full reference closure or retain it as historical only |
| [Requirements](../src/mos_eisley/project_requirements.py), [owner policy](../src/mos_eisley/project_guidance_policy.py) | `owner_uid` and mapped workspace; policy and requirements canonical bytes | Both 1; no policy activation solely because data was converted |
| [Frozen role context](../src/mos_eisley/project_guidance_role.py), [prepared guidance review](../src/mos_eisley/project_guidance_review.py) | `owner_uid`, mapped workspace and embedded frozen basis | Both 1; destination activation requires rebuilding context and review, not relabeling a prepared record |
| [Overrides](../src/mos_eisley/project_guidance_overrides.py), [conflict assessment](../src/mos_eisley/project_guidance_conflicts.py), [project assessment](../src/mos_eisley/project_guidance_precedence.py) | Indirect identity through bindings, requirements and basis records; exact `source_json`; enclosing canonical hashes | Saved records 1; outer versions and references change when a nested representation changes |
| [Task scope](../src/mos_eisley/task_state.py), [task archives](../src/mos_eisley/run/task_state_store.py) | `OwnerProjectScope.owner_uid/project_id/workspace_sha256`; task records embed this scope; manifest repeats owner/project/workspace and artifact hashes | Scope unversioned inside enclosing records; bundle 1/2, manifest 1. Version the enclosing task family independently and preserve historical authority records |
| [Author compaction](../src/mos_eisley/conversation_compaction.py) | Unversioned `CompactionScope.owner_uid/workspace_sha256`; source state/transcript, prior compaction, checkpoint and task bindings | Author record 1; retain verified historical evidence; regenerate destination active context instead of rewriting source digest claims |
| [SQLite store](../src/mos_eisley/run/conversation_sqlite.py) | Metadata `owner_uid`; state BLOB, serialized `SessionIndex.owner_uid`, header BLOB, entries and hash-addressed artifacts | `PRAGMA user_version=1` plus exact SQL schema comparison; copy to a distinct new database, no in-place metadata substitution |
| [Resume header](../src/mos_eisley/run/conversation_resume.py) | `owner_uid`, workspace and embedded compaction; derived from state and stored in SQLite | Header 1; regenerate from the selected destination generation |
| [OAuth controller](../src/mos_eisley/tools/mcp_oauth.py), [keychain store](../src/mos_eisley/tools/mcp_oauth_store.py) | `geteuid()` participates in a JSON binding digest along with resource, issuer, client, account and scopes; digest is the key under `mos-eisley.mcp.oauth.v1`; unversioned `OAuthRecord.binding` | Separate credential boundary. Preserve legacy lookup encoding; general artifact migration never copies tokens or silently rekeys credentials |
| [MCP HTTP settings](../src/mos_eisley/tools/mcp_http.py) | Optional `token_owner_uid` binds an environment-token reference; settings can be retained inside enclosing configuration | Currently unversioned settings; separately version the enclosing credential/configuration contract before platform adoption, preserving explicit null/default behavior and denying foreign token ownership |

## Preview, navigation and maintenance identities

These objects can be retained as receipts, but a retained observation is not a
fresh authorization to act. New schemas cannot reinterpret a legacy apply hash.

| Family and source | Identity-bearing data | Migration treatment |
|---|---|---|
| [Directory selection](../src/mos_eisley/conversation_directory.py), [relocation anchor](../src/mos_eisley/conversation_memory_identity.py) | Path/device/inode; a missing old path may be anchored to an existing parent | Temporary observations. Preserve old receipt bytes; reselect on the destination. Never manufacture an identity for an absent object |
| [Transfer](../src/mos_eisley/run/conversation_transfer.py), [export](../src/mos_eisley/run/conversation_export.py) | Plans carry `owner_uid`, source/destination `TransferLocation.device/inode` and snapshot selection hashes | Transfer plan 1; export plan **1/2**, where 2 already denotes another layout. Platform-aware export requires a distinct next version, not reuse of 2 |
| [JSON-to-SQLite migration](../src/mos_eisley/run/conversation_migration.py), [batch migration](../src/mos_eisley/run/conversation_batch_migration.py) | Selection hashes; batch owner UID and storage device/inode; unversioned individual receipt | Existing migration is a same-owner backend copy, not authenticated platform rebinding. Give platform migration its own kind and version |
| [Batch transfer](../src/mos_eisley/run/conversation_batch_transfer.py), [batch export](../src/mos_eisley/run/conversation_batch_export.py) | Embedded plans, aggregate selection hashes and bounds | Version enclosing plans/receipts whenever embedded wire forms change; report committed prefixes, not an invented all-or-nothing batch |
| [Retention](../src/mos_eisley/run/conversation_retention.py), [prune](../src/mos_eisley/run/conversation_prune.py), [batch prune](../src/mos_eisley/run/conversation_batch_prune.py) | Owner UID, root identity, store ID/generation; prune database and lock device/inode | Version-1 plan/receipt families; no import of apply authority. Build fresh destination plans after migration |
| [Temporary cleanup](../src/mos_eisley/run/conversation_cleanup.py) | Owner UID, storage identity, lock device/inode; file device/inode, size, mtime and ctime plus SHA | Version-1 plans/receipts. New identity objects do not replace byte hashes or metadata checks; old cleanup receipts are historical only |
| [Raw memory identity](../src/mos_eisley/conversation_memory_raw.py), [memory migration](../src/mos_eisley/conversation_memory_migration.py) | Receipt dictionaries with owner UID, device/inode, byte counts/timestamps; parent/root observations | Some dictionary forms have no version. Introduce a new explicit kind/version envelope; never extend an old hash body silently |
| [Guidance storage](../src/mos_eisley/project_guidance_storage.py) and memory/registry/guidance maintenance helpers | In-memory raw payload plus identity; reviewed backup, discard, staging-cleanup, retention and import previews reuse raw/parent observations | Preserve original receipts and backup filenames; classify each helper as a fresh-preview producer, not a transferable live binding |
| [SQLite page cursor](../src/mos_eisley/run/conversation_sqlite.py), [transcript cursor](../src/mos_eisley/run/conversation_transcript.py), [artifact selection](../src/mos_eisley/run/conversation_artifacts.py) | Owner UID, store ID, workspace, generation, session/snapshot/position selections | Currently unversioned encoded contracts. Give new forms explicit kind/version; new store ID/generation invalidates all old selections |
| [Skill tree inspection](../src/mos_eisley/run/skills.py) | `_EntryState` device/inode, link count, mode, size, mtime | Transient inspection snapshot, not a persisted principal schema. Reinspect through qualified storage APIs during later consumer adoption |

## Encoding and security boundaries

[Core contracts](../src/mos_eisley/core/models.py) reject extra fields and use strict,
frozen values. Canonical serialization uses UTF-8, sorted JSON keys, compact
separators and existing omission rules. Its SHA-256 hashes are not a license to
normalize original source JSON, optional fields or historical text. OAuth's legacy
binding uses its own `json.dumps(..., sort_keys=True)` encoding, including default
separators; it must not be replaced with the core canonical encoder under a v1 key.

Direct `getuid`/`geteuid`, mode/link checks, descriptor/path admission and SQLite
opening are separate consumer/platform contracts. Tagged identity does not replace
them. The inventory covers ordinary conversation, task, guidance, memory and MCP
identity surfaces; it does not authorize opening live private data or migrating
evaluation, signing or authorization stores. Such stores need their own audited
inventory and acceptance before adoption. Existing review/continuation artifacts
remain evidence under their original bindings, never destination permission.

## Implementation closure check

Before each implementation slice, use source searches for `owner_uid`, `getuid`,
`geteuid`, `device`, `inode`, `canonical_bytes`, `digest` and the selected scope's
imports to update this inventory against the exact target commit. Inspect source
and synthetic fixtures only. Check nested model validators, content-addressed paths,
SQLite exact-schema checks, CLI preview/apply decoders and optional-field omissions.
An unlisted discovered dependency blocks that slice; this document is not proof
that a future tree has the same closure.
