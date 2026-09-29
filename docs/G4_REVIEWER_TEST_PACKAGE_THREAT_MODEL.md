# Threat Model: G4 blind reviewer-test-package freezer

## Scope and ownership

- System/version: Mos Eisley starting at `195ef9c0b00c5b89ca78b033483bd526397343dc`.
- Owner/reviewer: Joshua Myers; implementation by Codex.
- Review trigger: new test-package schema, filesystem reader, marker detector or
  authority field.
- In scope: offline manifest/reference validation, package-file reads, immutable
  retention and verification. Out of scope: derivation models, test execution,
  implementation adapters, correction and VCS operations.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Approved derivation references | project-private metadata | exact digest and complete declared set | project owner |
| Reviewer-test bytes and oracles | executable/private | exact, complete, immutable, bounded | project owner |
| Frozen package artifact | private control evidence | canonical, content-addressed, replayable | project owner |

- Actors: package author, project owner, hostile package contents/filesystem, later
  binding/execution components, and a compromised same-UID process outside this
  boundary.
- Entry points: manifest JSON, ordered approved-reference paths, package root and
  output path.
- Data flow: bounded local reads -> pure validation/marker inspection -> private
  canonical output. There is no credential, network, subprocess or provider edge.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Traversal or symlink substitutes outside bytes | hostile paths/tree | freeze unrelated private data | canonical relative paths; directory-relative no-follow traversal; regular-file checks | negative filesystem tests | same-UID process can mutate accessible files, but opened bytes/digests are rechecked |
| Fixture/oracle changes while assertions stay fixed | incomplete package binding | false verification | every declared byte, role, size and digest is embedded and hashed | fixture/oracle mutation tests | semantic correctness remains independently reviewed |
| Hidden or stale skip/xfail | executable indirection | tests silently disappear | AST-based common-marker inventory must exactly match declarations | marker tests | aliases/dynamic wrappers require later runtime count checks |
| Empty or misleading collection | malicious manifest | vacuous success later | at least one matching test and exact expected collection count are frozen | schema tests | actual collection is a later execution-gate responsibility |
| Duplicate path, inode alias or special file | hostile tree | ambiguous/mutable package | unique sorted paths, unique opened inode identities, regular-file-only reads | alias/FIFO tests | remote filesystems may have weaker metadata semantics |
| Artifact treated as execution/write authority | downstream confusion | unauthorized code execution or mutation | literal false authority fields and explicit offline event | contract/CLI tests | downstream must continue to enforce its own authority |
| Malformed/oversized input | hostile input | memory/CPU exhaustion | strict schema, duplicate-key rejection, per-file/count/total bounds | boundary tests | Python parsing cost remains within declared artifact caps |

## Decisions

- Accepted risk: static marker detection is deliberately conservative and cannot
  prove semantics; later isolated execution must check collected/executed/skipped
  counts and known-good/known-bad controls.
- Required evidence: focused boundary tests, static analysis, full repository gate,
  and later independent approval before execution is enabled.
- Recovery: reject and recreate a new frozen package; never patch a frozen artifact.

