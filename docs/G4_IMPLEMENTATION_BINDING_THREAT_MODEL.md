# Threat Model: G4 allowlisted implementation binding

## Scope and ownership

- System/version: Mos Eisley at
  `8ca3e3d7a54f3870ef4aa7815a7007e07119a184`.
- Owner/reviewer: Joshua Myers; implementation by Codex.
- Date and review trigger: 2026-09-24; new implementation-tree reader, declarative
  adapter schema or binding authority field.
- In scope: offline package/tree identity checks, exact source-root inventory,
  dependency/build declarations, direct-symbol allowlist and immutable binding
  record. Out of scope: Git attestation, test execution/containment, runtime adapter
  materialization, known controls, correction and acceptance.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Frozen reviewer-test package | executable/private | unchanged before and after binding | project owner |
| Implementation source/resources | private executable inputs | complete source-root inventory and exact bytes | project owner |
| Dependency/build inputs | supply-chain control | exact reviewed declarations | project owner |
| Declarative adapter and binding record | private evidence | canonical, immutable, replayable, non-authorizing | project owner |

- Actors and capabilities: binding-manifest author, project owner, hostile reviewer
  package, hostile implementation tree/filesystem, later isolated runner, and a
  compromised same-UID process outside the boundary.
- Entry points and trust boundaries: binding-manifest JSON, canonical frozen package,
  implementation root and output path.
- Data flows and external dependencies: bounded local file reads and AST parsing to a
  private canonical record. No import, subprocess, Git, credential, network or
  provider edge exists.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Executable adapter fakes output or swallows errors | adapter can run arbitrary code | false passing evidence | fixed declarative direct-symbol schema; all wrapper/mutation/interception authorities false | adapter-negative tests | later runner must materialize only this schema |
| Reviewer bypasses adapter with a direct import | hostile package source | unaudited binding surface | scan every frozen Python file; exact explicit adapter imports; reject target-package imports and wildcards | import-surface tests | dynamic import/metaprogramming requires runtime controls |
| Manifest omits source/resource files | incomplete inventory | stale or hidden implementation behavior | enumerate every regular file under non-overlapping source roots and compare exact declarations | hidden Python/resource tests | selected source-root completeness remains reviewable policy |
| Dependency or build input changes | stale declaration | wrong environment identity | require lock and build metadata; bind exact bytes and tree digest | drift and schema tests | generic code cannot infer every project-specific dependency input |
| Symlink, hard link, FIFO or alias escapes the root | hostile filesystem | bind unrelated/mutable bytes or hang | no-follow dirfd traversal, regular-file and single-link checks, unique inode set, nonblocking opens | filesystem-negative tests | malicious same-UID replacement between separate reads is not fully preventable |
| Package changes after implementation is revealed | race or post-freeze mutation | blindness/binding mismatch | canonical package required; hash/read before and after tree inspection | package-race test | transient change-and-restore by same UID may evade observation |
| Huge/deep tree exhausts binder | hostile source root | denial of service | manifest/file/byte caps plus 4,096-entry and 64-directory-depth walk limits | boundary tests and constants | filesystem calls still consume bounded local work |
| Claimed source revision is treated as Git proof | unauthenticated manifest | false provenance | record labels it a claim; exact tree digest is authoritative; no VCS authority | docs and false authority fields | trusted VCS/E2 gate remains required |
| Binding record is mistaken for execution/acceptance | downstream confusion | unauthorized effects | literal false authority fields and non-executing CLI | contract/CLI tests | downstream components must re-enforce their own gates |

## Decisions

- Accepted risks with owner and expiry: static Python inspection cannot exclude
  dynamic imports or runtime monkeypatching, and manifest review must establish the
  complete dependency/build surface. Joshua Myers owns these residuals until the
  isolated runner, known-control and trusted VCS/E2 slices close them.
- Required tests and monitoring: focused schema/filesystem/race/import tests, static
  analysis, full repository suite, built-wheel smoke, then later isolated runtime
  collection and known-good/known-bad receipts.
- Incident and recovery dependencies: reject the record and create a new manifest and
  binding version. Never patch an immutable record or loosen the frozen oracle.
