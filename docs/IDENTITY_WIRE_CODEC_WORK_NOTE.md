# Inert identity wire codecs verification

Status: implementation complete; full combined gate passed. Owner: Josh Myers. Date: 2026-10-03. Base: f638e6b with the
uncommitted migration inventory/design carried forward on `feat/identity-wire-codecs`.

Objective: implement the pure standalone principal/file/owner-binding codecs from
[the design](IDENTITY_MIGRATION_DESIGN.md) and freeze selected synthetic legacy
bytes/hashes. Preserve legacy readers/writers and public platform refusal. No OS
queries, namespace enrollment, migration authority, credentials or storage effects.

Guidance: Python engineering guide, agentic verification guide/loop, work-note and
threat-model templates, adversarial review guide, existing identity threat model
and proposed ADR-0015. Risk: untrusted serialized identity boundary. Acceptance:
M-02/03/05/06 for this slice, including strict exact shapes, 4,096-byte preparse
bound, full-width fields, duplicate-key/encoding/version refusal, immutable metadata,
legacy golden fixtures and inert source/fresh-wheel execution. Selected fixtures
cover memory (explicit null/defaults and non-ASCII text), snapshot digest, mapped
registry directory IDs, omitted optional evidence fields and OAuth's distinct
legacy JSON binding encoding and MCP HTTP token-owner settings. Existing owner/storage regression tests supplement
fixtures; this slice does not define new durable artifact versions or migrate them.

Ceiling: three correction passes and three hours active implementation, excluding
long gates. Stop after focused tests, static checks, source/wheel qualification and
reference/diff checks; run the repository combined gate before publication.
Accountable boundary review and native selector/storage admission remain open.

## Evidence and handoff

Implemented `platform.identity_wire` using only the standard library and the
existing pure identity values. Public encode/decode functions cover principals,
opened-file identities, immutable `OwnerBinding` and `ScopedFileIdentity`. Exact
member sets, tags, strict integers, lowercase full-width hex, duplicate keys at
every depth, bounded UTF-8 and exact canonical JSON refuse invalid/unknown forms.
The decoder checks size before parsing; diagnostics omit input identifiers. No
namespace is enrolled and no OS, storage or credential query is performed.

Six frozen synthetic byte/digest fixtures cover memory, its snapshot, a mapping
registry with full-width directory IDs, omitted evidence fields, OAuth binding and
HTTP token-owner settings. Tests invoke unchanged legacy readers, retain old backup
filenames/null/default/non-ASCII behavior and verify refusal of new owner/version
fields. The OAuth constructor test replaces the entire store, never the real vault.

Verification on macOS/Python 3.12:

- Final focused source run: 20 tests passed (13 wire and seven legacy fixture tests).
  The initial fixture run caught a wrong test-only OAuth config module path; corrected
  before final source/wheel runs. Static checks caught and corrected redundant casts,
  test annotations and formatting; no legacy/runtime implementation changed.
- Selected platform, registry, guidance-binding and compaction regression run:
  140 tests, 132 passed/eight native-Windows skips. This run preceded one added
  preparse-limit/diagnostic test; the final focused run and wheel runs include it.
- Focused wire coverage: 123 statements and 44 branches, 100% covered. This is
  module coverage, not the repository-wide coverage gate.
- Fresh dependency-free wheel smoke: 92 platform tests, 84 passed/eight native
  skips, plus two portable frozen-fixture tests passed. Module paths were verified
  under the fresh environment. The native smoke selection now includes wire and
  portable fixture tests; CI also runs wire tests from Windows source.
- A separate fresh wheel with hash-pinned `requirements.runtime.txt` dependencies:
  all 20 wire/legacy tests passed outside the source tree. Installed module origins
  were verified under that environment; dependencies were installed from cache.
- Repository-wide Ruff lint/format, strict Pyright, runtime-export verification,
  sdist/wheel build and `git diff --check` passed.
- Readback: all 433 relative Markdown links resolve, no design/implementation
  placeholders remain, and the source change inventory contains only the additive
  `identity_wire.py` module. Both fresh-wheel checks were repeated after the final
  synthetic MCP HTTP fixture addition and final artifact build, with the same
  passing counts above.

Disposable wheel evidence: `/private/tmp/mos-identity-wire-platform-wheel.log` and
`/private/tmp/mos-identity-wire-fixtures-wheel.log`. Source and wheel checks exercise
M-02/06 and the selected legacy/new-version refusal portions of M-03/05. Other
artifact families, rollback, new durable schema acceptance and native qualification
remain open. The subsequent full combined gate below supersedes the earlier
unpublished-batch limitation.

Handoff: `feat/identity-wire-codecs` contains the migration inventory/design
and this implementation in one commit scope. Existing reader/writer/selector modules and dependencies
are unchanged. Source and installed-wheel CI include the new tests; actual CI for
this branch and accountable boundary review are pending. Before publication,
reconcile adapter PR ancestry with current main. Next is protected namespace
enrollment and qualified storage prerequisites, not writer adoption or rebinding.

## Full combined gate before commit — 2026-10-04

`make check` passed with exit status 0 against the combined codec, fixture, CI and
inventory/design batch. Ruff lint/format and strict Pyright passed. The source suite
ran 2,786 tests in 2,400.154 seconds, with 12 skips and no failures; aggregate coverage with branch
measurement enabled reported 86%, passing the configured threshold. Runtime-export verification
and sdist/wheel build passed. Full installed-wheel smoke ran 2,031 tests in
1,632.941 seconds, with eight skips and no failures. Native Windows tests remain
skipped on this macOS host; this gate grants no native admission or accountable
boundary review.

The initial sandboxed invocation was interrupted before completion after a direct
localhost bind probe confirmed sandbox refusal. The complete gate then ran with
approved access for localhost and tmux fixtures; no implementation corrections
were needed. Disposable combined log:
`/private/tmp/mos-identity-wire-make-check.log`. Only documentation recording this
result changed after the successful gate; whitespace/reference checks were repeated
before committing. No push, pull request or merge is part of this commit request.

## PR publication and exact secret-scan finding — 2026-10-04

PR #270 targets main and depends on still-open adapter PRs #268/#266. Fetched main
`b3546f9` is already an ancestor; no integration/code change was needed. GitHub's
8.24.3 secret scan reported one `generic-api-key` finding at the introducing commit
`6079b3f`, `tests/test_identity_legacy_fixtures.py:34`: the frozen `OAUTH_SHA` fixture
digest. It is SHA-256 of the literal synthetic UID/resource/issuer/client/account/
scopes binding, using reserved `.invalid` endpoints, not credential material.
The literal digest is verified by the existing fixture and controller tests.

Following existing repository practice, `.gitleaksignore` adds only the exact
commit/file/rule/line fingerprint. No rule, path or future finding is exempted.
Only scanner metadata and this verification record changed after the full gate;
affected synthetic fixture/hash checks were rerun. The follow-up scan result is
tracked on PR #270; full source/package/native CI and accountable review
remain separate publication/admission gates.
