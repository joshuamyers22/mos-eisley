# Agentic Verification Loop: G3 single-human oracle planning record

## Objective and authority

- Requirement: Joshua approved planning a narrow objective-oracle G3 study with him as only human.
- User journey: a reviewer can see the allowed claim, proposed values, source candidate and unresolved empirical gates without mistaking a proposal for a label seal.
- Invariants: no invented labels, groups, probabilities, signatures or splits; no restricted store access; no bypass of existing verifier rules.
- Risk class: high-risk governance and statistical design.
- Implementation owner: Codex for documentation; Joshua Myers for accountable study decisions.
- Starting revision: `37a246c20e93eaf3a9657f660b2ed676b355cc5a`, clean worktree.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| G3 claim scope | Blocking | ADR, plan, roadmap and G3 guide | Explicit narrow frame and broad G3 still open |
| Verifier truthfulness | Blocking | Schema/guide inspection | Existing two-grader and audit rules stated; no signatures asserted |
| Source and statistics | Blocking | NIST source page and proposed protocol | Candidate identified; no unreviewed IID/sample claim |
| Data boundary | Blocking | Changed-file inspection | No restricted stores or raw case/outcome content |

## Budget and stopping rules

- Maximum iterations: two evidence-changing passes.
- Spend: zero provider/study spend.
- Pass rule: documentation consistency and repository gate pass; empirical gates remain explicitly open.
- Stop/escalation: source, oracle, statistical margins, budget and operational custody require owner review before an empirical seal.

## Iterations

| # | Implemented slice | New evidence/context | Findings | Decision and correction | Gates |
|---:|---|---|---|---|---|
| 1 | ADR and linked plan/guide/roadmap | Existing schema and ADR-0008 | Existing catalog cannot express one-human oracle exception | Preserve existing seal rule; require amendment | Documentation review pending |
| 2 | Review-package status and source audit | NIST suite page, v1.3 archive checksum, guide and technical note | Answer cues, related cases and oracle limits block the original 400-group study | Record conditional verdict and require validated subset | Local links and `git diff --check` passed; full gate passed outside sandbox |

## Exit

- Stop reason: planning record complete; empirical source and method require accountable owner input.
- Blocking findings: none for documentation; a qualified source subset, oracle, grader/verifier, costs and registration remain open.
- Full quality gate: first `make check` passed lint/type checking, then failed with 31 `PermissionError: [Errno 1] Operation not permitted` test errors, all from localhost HTTP/OAuth fixture socket binding in the managed sandbox. The required outside-sandbox `make check` completed with exit 0: lint and type checking passed; 2,540 source-tree tests passed with 4 skipped; export verification, package build and 1,894 installed-wheel smoke tests passed.
- Human/domain approval: Joshua approved narrow direction; no spend, label or cohort approval inferred.
- Durable facts: ADR-0010 and updated G3 documents and project memory.
