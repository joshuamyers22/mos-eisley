# Identity migration design verification

Status: documentation complete; included in the codec batch. Owner: Josh Myers. Started:
2026-10-03. Base: f638e6b, separate
`docs/identity-migration-design` worktree while candidate adapter PR #268 runs.

Objective: inventory the existing persisted principal and opened-file identity
representations under [plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support),
then define a proposed versioned migration contract, recovery model and acceptance
matrix. This batch changes documentation only. No new writer, reader, migration
command, private-storage policy, public Windows selector or runtime adoption.

Invariants: preserve original legacy bytes, canonical encodings and hashes; no
UID-to-SID inference, cross-host file-ID equivalence, automatic ownership rebinding,
authority transfer or stale preview reuse. Native qualification and accountable
review precede writer/consumer adoption. Audit repository source and synthetic test
definitions only; do not inspect private live stores or sampling artifacts.

Selected guidance: [verification guide](AGENTIC_VERIFICATION_GUIDE.md),
[verification loop](../templates/AGENTIC_VERIFICATION_LOOP.md),
[work-note template](../templates/WORK_NOTE.md),
[threat-model template](../templates/THREAT_MODEL.md),
[adversarial review guide](ADVERSARIAL_REVIEW_PLAYBOOK.md),
[review template](../templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md),
[ADR template](../templates/ADR.md), existing identity contract/threat model and
ADR-0014. The write-page skill supplies prose/readback guidance; the destination
and established Markdown format remain the repository documentation.

Blocking rubric: M-01 source-linked inventory distinguishes durable artifacts,
derived indexes and transient preview identities; M-02 unambiguous tagged wire
forms and scope/owner binding; M-03 legacy byte/hash preservation and downgrade
refusal; M-04 explicit prepare/publish/recover/rollback contract; M-05 concrete
positive/negative acceptance cases and implementation dependencies; M-06 source
references, document links and unchanged runtime verified. Risk: proposed native
identity/schema trust boundary. Ceiling: three correction passes, three hours active
work excluding existing long gates. Stop when documentation, bounded source/test
inspection and link/diff checks satisfy this rubric. A full implementation gate is
required before later code publication; this design pass claims no code or native
qualification result and no independent/accountable review.

## Evidence and handoff

Delivered the [source inventory](IDENTITY_MIGRATION_INVENTORY.md),
[proposed design](IDENTITY_MIGRATION_DESIGN.md) and
[ADR-0015](adr/0015-versioned-identity-migration.md). Updated §27.2, roadmap,
identity contract, threat model, ADR-0014 and the durable project-memory index.
The inventory separates durable/nested owners, saved directory bindings, SQLite
metadata/derived state, navigation and maintenance observations, and implicit
OAuth key bindings. The design defines exact wire forms and bounds, proposed
version allocation, protected owner namespaces, legacy decoding/byte preservation,
rebinding prerequisites, publication/recovery and M-01–M-16 future acceptance.

Existing source compatibility verification used the parent worktree's Python 3.12
interpreter/dependencies with `PYTHONPATH=src:tests` in this worktree; no private
stores or real keychains were opened. The following 97 unique tests passed:

- 71 tests across `test_conversation_migration`, `test_conversation_export`,
  `test_conversation_memory_registry`, `test_project_guidance_binding` and
  `test_conversation_compaction`: retained history/bytes, owner/canonical checks,
  preview refusal, changed selections, publication/flush failure and recovery.
- 20 tests in `test_mcp_oauth`: fake-keychain owner/account/binding isolation and
  credential lifecycle. The initial combined 91-test run had 20 setup errors
  because sandboxing denied the fixture's localhost socket bind. Re-running only
  the affected OAuth module with escalation passed all 20; no implementation
  correction was needed. These fixtures do not use production OAuth credentials.
- Six selected SQLite/task tests: artifact round-trip, permissions/schema/owner
  refusal, stale/foreign cursors, private archive owner scope, tampered/missing
  artifact refusal and schema-1 recorded-run compatibility.

Readback/reference checks for the completed design-only pass: all 420 relative file links in the ten changed Markdown
files resolve; no TODO/TBD remains in the new documents; `git diff --check` passes;
tracked/untracked change inventory contains documentation only. Pure-value source
constraints, exact SQLite schema checks and current family versions were checked
against source. These checks establish the documented baseline; they do not pass
the proposed new codec/migration acceptance matrix.

PR #268 remains open at `f638e6b`: its observed Windows-files, container and
secret-scanning checks passed; source/package were still running at the status
check during this batch. No merge or public-selector admission was performed.

Design-only handoff: branch `docs/identity-migration-design` was based on the still-open adapter
branch. Reconcile its ancestry with merged main before eventual publication.
The next smallest implementation batch is inert wire codecs plus frozen legacy
fixtures; no writer or consumer adoption. Native qualification, protected
namespace/storage prerequisites, accountable design review and actual migration
acceptance remain open. `make check` and a fresh installed-wheel run were not
repeated for this documentation-only, unpublished batch; run the required combined
gate before publication. No independent review or native qualification is claimed.

## Subsequent implementation handoff

The user subsequently requested the inert codecs and legacy fixtures. The local
unpublished branch was renamed `feat/identity-wire-codecs` with all design changes
retained. [The codec work note](IDENTITY_WIRE_CODEC_WORK_NOTE.md) records the new
source/wheel implementation evidence and supersedes the next-batch handoff above.
Existing writers/readers, storage authority and native admission remain unchanged.

The user subsequently authorized the full combined gate and commit on 2026-10-04.
[The codec verification record](IDENTITY_WIRE_CODEC_WORK_NOTE.md#full-combined-gate-before-commit--2026-10-04)
records the passing source, coverage, export, build and installed-wheel results for
this combined inventory/design/implementation batch. The earlier design-only
verification limitation above is historical; native and accountable admission
remain open.
