# Namespace-record and storage-admission contract verification

Status: definition complete; implementation and qualification pending. Owner: Josh Myers. Date: 2026-10-04. Base: 4d0dd7a, separate
`docs/namespace-storage-contract` worktree while the codec PR is under review.

Objective: freeze the smallest versioned namespace record and read-only admission
contract needed before protected enrollment. This is a definition batch: no record
writer, namespace creation, key enrollment, migration consumer, existing storage
replacement or public Windows selector admission. Complete the design prerequisites
and ordered acceptance/handoff; implementation and native qualification follow.

Invariants: a decoded namespace is metadata; current-principal equality and private
storage alone do not prove enrollment. Preserve legacy bytes/hashes and existing
consumer behavior. Refuse unknown protection/namespace/filesystem scope, stale or
closed references and unsupported native contexts. No on-read creation/repair,
credential fallback, enrollment inference or authority transfer. Inspect repository
source and synthetic fixtures only, never private live stores or sampling artifacts.

Guidance: repository working agreement, verification guide/loop, work-note,
threat-model and ADR templates, adversarial review guide, prior identity/migration
contracts and ADR-0015. Repository Markdown destination follows the previously
applied write-page guidance. Risk: new namespace and private-storage trust boundary.
Definition rubric: C-01 exact bounded record; C-02 clear storage-versus-enrollment
trust states; C-03 borrowed/owned lifetime and bounded read-only effects; C-04
qualified POSIX and native DACL/reparse/filesystem refusal; C-05 enrollment,
publication and recovery gates; C-06 source-linked acceptance, efficient
implementation order and unchanged runtime. These are document review criteria;
the contract separately numbers future implementation tests N-01 through N-16.
Ceiling: three correction passes, two hours active work; stop when those definition
checks and source/link/diff checks pass. Full combined gate is required before
publication; this documentation pass grants no accountable/native admission.

## Evidence and handoff

The [contract](NAMESPACE_STORAGE_CONTRACT.md) and
[ADR-0016](adr/0016-namespace-record-storage-admission.md) define the five-member
version-1 record, distinct metadata/storage/enrollment states, owned directory
lease and fixed-child reader. The migration design, plan §27.2, roadmap, identity
contract/threat model, ADR-0015 and project memory link the preparation and its
ordered follow-up. All ten changed files are Markdown; runtime and existing
selectors are unchanged.

Source-based readback identified gaps between existing owner/mode/link checks and
namespace admission. The contract requires actual ACL inspection, freezes the
initial private-mode/DACL and lease-right policies, distinguishes held-root reads
from pathname-anchor validation, and specifies idempotent close and refusal on
uncertain cleanup. Enrollment requires a separately protected anchor and custody
proof; copied private JSON never supplies either. These revisions address C-01
through C-06 as definition checks, not implementation passes or independent review.

Existing synthetic regressions passed using Python 3.12 with this worktree's
`src:tests` on `PYTHONPATH`: `test_platform_identity`,
`test_platform_identity_wire`, `test_identity_legacy_fixtures`, SQLite permission,
link, schema and owner refusal, and stale/foreign workspace/database cursor refusal.
Result: **42 tests passed in 0.611 seconds**, no skips. These are existing baseline
checks, not the future namespace acceptance suite. Relative repository links and
N-01 through N-16 acceptance-row coverage were checked; `git diff --check` passed.

No namespace API, protected enrollment, storage admission or Windows release
qualification is implemented by this batch. Native allocation bounds, descriptor
ACL/mount policy, secure relative opens, custody persistence, lock/publication and
crash recovery need real target evidence and accountable review. The full combined
`make check` gate and publication remain pending for this documentation branch;
no commit or push was requested.

Next: implement only the pure namespace-record codec and exact golden fixtures
(N-01/02/03/14), preserving inert imports and existing legacy bytes. Subsequent
read-only POSIX root admission and fixed-child reads must qualify separately.
Writers, automatic adoption/repair and public Windows selectors remain gated.
