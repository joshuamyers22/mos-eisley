# Agentic Verification Loop: G4 blind reviewer-test-package freezer

## Objective and authority

- Requirement: roadmap G4; plan §26.4; adversarial-loop plan Phase L2.
- Outcome: freeze one independently derived Python reviewer-test package as an
  immutable, content-addressed artifact before implementation or author telemetry is
  revealed.
- Invariants and non-goals: bind exact approved plan/interface/rubric/creator inputs;
  retain every declared test, fixture, input, expected value, parameter, oracle and
  collection setting; detect declared skip/xfail sites; reject mutable aliases,
  traversal, symlinks and byte drift; grant no execution, implementation binding,
  repository write, VCS, credential, network, provider, correction or acceptance
  authority.
- Risk class: high-risk new executable-artifact trust boundary.
- Implementation owner: Codex under Joshua Myers's direction.
- Accountable approval: Joshua Myers; this offline slice does not approve execution.
- Starting revision: `195ef9c0b00c5b89ca78b033483bd526397343dc`, clean worktree.
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and
  `templates/WORK_NOTE.md`.

## Rubric

| Dimension | Severity | Evidence | Pass threshold |
|---|---|---|---|
| Immutable complete package | blocking | Canonical artifact and round-trip/tamper tests | Every declared byte and collection field is retained and content-addressed |
| Blind derivation boundary | blocking | Input schema and CLI/source inspection | Only approved plan/interface/rubric/creator/marker-approval references are accepted; no implementation or author-telemetry input exists |
| Hostile filesystem handling | blocking | Traversal, symlink, special-file, alias and mutation tests | No declared byte can escape or alias the package root; unsafe input fails closed |
| Marker integrity | blocking | Python syntax and skip/xfail mutation tests | Detected and declared markers match exactly; stale or undeclared markers reject |
| Authority separation | blocking | Schema/CLI assertions | Artifact fields literally deny execution, binding, writes, VCS, network, credentials and provider use |
| Delivery quality | high | Focused and repository gates | Ruff, formatting, Pyright, focused tests and `make check` pass |

## Budget and stopping rules

- Maximum passes: implementation, focused fault tests, adversarial source review,
  then the repository gate.
- Provider spend: USD 0; no provider or network calls.
- Pass rule: every blocking rubric row passes and no unresolved high finding remains.
- Stop/escalate: stop if semantic blindness or arbitrary executable-code equivalence
  is required; those require later independent review/runtime evidence.
- Rollback condition: any path escape, unbounded read, mutable external dependency,
  undeclared marker, or authority-bearing output.

## Iterations

| # | Slice | New evidence | Findings | Decision | Gates |
|---:|---|---|---|---|---|
| 1 | Contract and threat boundary | Phase L2 requirements and existing canonical/private-artifact patterns | The initial design could admit a declared test outside the collection rule and reuse one marker approval for multiple markers | Require every declared test to be selected and require a unique approval reference per marker | Focused red/green regressions |
| 2 | Immutable freezer and hostile-input probes | Canonical round trip, byte/reference drift, malformed Python/JSON, path, alias, special-file, marker and CLI tests | No unresolved implementation finding | Retain an inert, self-contained package with literal non-authority and fail-closed filesystem reads | 9 focused tests pass; Ruff, format and Pyright pass |
| 3 | Adversarial source-level review | AST marker inventory and manifest claims were compared with Python's dynamic behavior and the trust boundary | Static syntax cannot prove marker semantics or reviewer independence | State the limitation explicitly; require later observed-count and authenticated derivation gates | Threat model and package guide updated |
| 4 | Repository and built-artifact verification | Full source discovery, loopback-capable MCP retry, export verification, package build and installed-wheel smoke | The managed sandbox denied 31 localhost fixture binds; no product failure was found | Classify those 31 errors as environmental after the complete affected family passed with loopback permission | 2,440 source tests accounted for with 4 skips; 48 affected MCP tests pass; 88% coverage; export and build pass; 1,787 installed-wheel tests pass |

## Finding disposition

| ID | Evidence | Consequence | Severity | Disposition | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| G4-TP-001 | A test declaration outside the frozen discovery start/pattern was initially accepted | A later runner could omit reviewer-authored assertions | blocking | Fixed: every declared test must be selected by the exact collection contract | Unselected-test and mismatched-pattern regressions | Joshua Myers |
| G4-TP-002 | One marker-approval reference could initially be shared by multiple declared markers | Approval scope could be silently broadened | blocking | Fixed: marker approvals and declarations are an exact one-to-one set | Reused-approval regression | Joshua Myers |
| G4-TP-003 | Python aliases, wrappers and runtime construction can evade or alter a static marker scan; self-description cannot prove mental independence | The freezer alone cannot establish semantic execution counts or blind authorship | high | Accepted for this inert slice and deferred to authenticated derivation plus isolated runtime count/known-control gates | Explicit documentation, literal authority denial and no execution path | Joshua Myers |

## Exit

- Stop reason: the bounded offline freezer slice is implemented and verified; G4's
  downstream binding and execution work is intentionally not authorized here.
- Rubric result: every blocking row passes; G4-TP-003 is an explicit residual
  limitation assigned to later G4 gates.
- Full quality gate: passed when the known sandbox-only localhost cases are accounted
  for by their successful loopback-capable rerun.
- Remaining uncertainty: static marker discovery and signed digests cannot prove
  semantic independence; later binding/execution gates remain required.
