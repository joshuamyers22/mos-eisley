# Windows root security contract verification

Status: definition complete; implementation, native acceptance and accountable
review pending. Owner: Josh Myers. Date: 2026-10-04. Baseline: `c42eec8`.
Branch: `docs/windows-root-security-contract`, separate worktree stacked on the
POSIX reader batch. No existing changes were present when this branch was created.

Define the smallest Windows root-admission slice under
[plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support):
[bounded owner/DACL inspection](WINDOWS_ROOT_SECURITY_CONTRACT.md) of an already-open
local-NTFS directory, with a pure parser first and native implementation only after
prerequisite identity review. Owned leases, relative child reads, public selectors,
enrollment/custody, existing consumers and writers remain separately gated.

Selected guidance: Python engineering and bounded verification guides, adversarial
review playbook, work-note/verification-loop/threat-model templates and ADR-0016.
The previously applied write-page guidance uses this repository Markdown destination.
Risk: material private-storage/native-allocation definition. Assets are private
owner/DACL integrity, query-buffer and token/reference lifetimes, and separation
of observations from authority. Untrusted descriptor bytes and concurrent same-owner
changes are in scope; kernel/admin/trusted-process compromise is excluded.

Definition rubric: D-01 smallest query-only scope and separate ownership/child work;
D-02 exact bounded synchronous buffers and checked relative extents; D-03 frozen
owner/DACL and handle-right profiles; D-04 fresh principal/object observations and
bounded cleanup; D-05 real source/wheel/SDK acceptance vs portable faults; D-06
source/primary-reference traceability and unchanged runtime. These are document
checks, not future WS-01–WS-11 implementation passes. Ceiling: three corrective
passes, 90 minutes active work. Stop after rubric/readback/link/diff and selected
existing boundary regressions pass. Full gate remains required before publication.

## Source findings and design decisions

- Microsoft's GetKernelObjectSecurity accepts caller-supplied output storage.
  The proposal uses a fixed 64 KiB descriptor buffer, no sizing/growth loop, two
  fresh successful observations maximum and no allocator-returning security API.
- Fixed granted-access and directory/tag/basic queries supplement full local-NTFS
  identity. The existing file identity adapter does not establish private DACL,
  directory-only, delete-pending or reparse policy. The new definition makes those
  independent requirements explicit rather than crediting identity tests with them.
- Owner full control (`0x001F01FF`) is the DACL policy, distinct from query rights
  (`0x00120080`) and future owned-directory lease rights (`0x001200A1`). Source
  granted-rights validation precedes any later duplication. The first inspector
  never duplicates/closes the borrowed directory.
- The descriptor profile accepts protected explicit owner-only ACL revision 2 and
  control `0x9004`/`0x9404`. The optional auto-inherited bookkeeping bit grants no
  ACE inheritance; all ACE flags must still be zero. Unknown/defaulted/unprotected
  or additional-trustee forms refuse. Native qualification must demonstrate the
  proposed encodings instead of silently expanding them.
- Current principal cleanup attempts owned token close and refuses failed close,
  but has no uncertain-token/acquisition-disable state. Existing tests check close
  attempts/refusal, not a bounded repeat after uncertainty. Identity prerequisite
  review must resolve this before native root security implementation claims
  bounded cleanup. The gap is documented; no fix or review approval is inferred.

The definition includes abuse controls for unbounded descriptor output, unchecked
pointer/offset/ACE traversal, generic-right aliases, inherited/foreign grants,
borrowed-reference mutation, stale observations and uncertain token/native output
lifetimes. Syntax/private permissions/candidate metadata cannot grant enrollment.
Native positive and negative fixtures use only explicitly created synthetic roots;
remote/removable and other unavailable cases require separately recorded evidence.

## Verification and handoff

Primary Microsoft API/layout/control/rights references were read and linked in
the contract. Source trace covers the existing identity adapters and portable
fault/cleanup tests. Changes are documentation only; runtime, fixtures, CI and
dependencies are untouched. Native Windows execution is not available here and
no new parser, inspector, lease or WS acceptance test is claimed implemented.

Verification: local Markdown link targets resolve; fixed-size ABI arithmetic,
query/lease/full-control masks, descriptor control values and SID bounds agree;
WS-01–WS-11 are present. Selected existing storage/namespace/principal/file fault
and native-binding regressions pass from this worktree: **45 tests, no skips**
on the macOS host. These establish the unchanged portable baseline, not new native
Windows acceptance. `git diff --check` passes. The full `make check` publication
gate was not run for this documentation-only definition and remains required
before publication. Accountable approval remains pending. No commit, push or PR
is requested.

Subsequent implementation: the [pure parser and synthetic fixtures](WINDOWS_SECURITY_PARSER_WORK_NOTE.md)
are now implemented separately. The statements above describe the definition
snapshot. Native inspector implementation still follows prerequisite identity
review and resolution of token-release uncertainty, then actual Windows
source/wheel evidence.
