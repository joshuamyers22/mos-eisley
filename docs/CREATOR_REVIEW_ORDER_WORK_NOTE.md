# Creator implementation-review ordering correction

- Status: source correction and both local full gates passed. Owner Joshua Myers; operator Codex.
- Started: 2026-10-30 UTC. Base: immutable rc.11 `4d927ce`, storage epoch 2.
- Requirement: correct RC11-SUB-01's conflicting creator workflow instructions in
  a new candidate. Prior failed campaigns and published rc.11 remain immutable.

## Objective, context and rubric

Make the creator's instructions match the enforced live sequence: freeze/review
plan and tests, exact creator approval, coding-child dispatch, frozen candidate
tests, independent implementation review and exact creator approval before
integration, then fresh tests of the integrated tree. Update the project plan's
ambiguous integration/review ordering to match that existing contract.

Selected guidance: repository AGENTS/CONTRIBUTING, Python engineering guide,
bounded verification guide/loop and work-note template, using the repository's
production-template pin. Context: `conversation_planning.py`, the creator and
review packets in `conversation_live_coding.py`, plan sections 14/15.7, the
planning/live-workflow tests, and PR #343's rc.11 qualification review.

Risk: material instruction correctness and context admission. The runtime review,
spending, identity, containment and storage gates remain authoritative. Preserve
exact plan/test/candidate bindings, zero implicit authority, rejection before
integration, protected tests, and legacy recorded bytes. Retain frozen candidate
dependencies and main's separate newer dependencies. No provider inference,
campaign renewal/replay, release signing or publication is part of this bounded
source correction; those require exact-candidate qualification/disposition.

Acceptance evidence: the actual controller-selected author request and creator
packet convey the same pre-integration order; existing plan/final-review refusal,
both-store persistence and context-admission cases pass; strict lint/type checks
and the combined full source/wheel gate pass on candidate and main integration.
Use rc.12 metadata without retargeting rc.11.

## Budget and stopping rules

One coherent implementation batch, focused affected checks, then one full
`make check` per dependency set (four-hour ceiling each). Additional corrections
require a concrete failed check. Provider invocations: zero. Stop dependent work
on failing checks, unexplained input changes, ancestry mismatch or new authority
requirements. Commit/push only the exact fully tested batch; protected PR CI
precedes normal integration. Unsigned source tests do not establish signed or
installed live acceptance.

## Observations and handoff

RC11-SUB-01's creator plan placed final review after integration. Both critics
accepted the plan; the judge requested pre-integration review. All received the
new real execution receipt. The shared author instruction and general plan text
conflict with the live creator/review prompts and enforced integration gate.
Current action: correct those instructions and verify the delivered request.

## Verification observations

- Both dependency sets passed 16 planning cases and 25 live-workflow cases,
  including the actual controller-to-creator packet regression; lint/format and
  strict typing passed.
- Initial parallel full source runs were nonpassing: candidate 3,893 cases with
  one existing memory-project SQLite CLI timeout; integration 3,895 cases with
  one existing memory-mapping SQLite CLI timeout. Both retain 17 skips and
  unchanged input manifests. Logs/results remain separately retained.
- Unchanged isolated diagnostics passed: candidate's seven memory-project and
  ten memory-mapping cases, plus the exact integration memory-mapping case.
  Deadlines remain 15 seconds. Concurrent-run resource contention is a hypothesis,
  not an established product cause. One sequential full rerun per tree is the
  bounded execution-environment check; no product/test changes or suppression.

## Final combined gates

| Tree | Source suite | Installed-wheel suite | Coverage | Full elapsed |
|---|---|---|---|---|
| Frozen rc.12 candidate | 3,893; 17 skips; 2,871.201s | 2,868; 13 skips; 1,961.081s | 86% | 4,891.083s |
| Main dependency integration | 3,895; 17 skips; 2,786.749s | 2,880; 13 skips; 2,046.948s | 86% | 4,893.143s |

Both full `make check` gates returned zero, including lint/format, strict Pyright,
export verification and build. The exact file sets and hashes of all 856 candidate
and 857 integration non-Markdown inputs remain unchanged. Both full reruns are
within their four-hour ceilings. The failed parallel runs remain nonpassing
history; no code, tests or deadlines were changed to obtain the serial passes.

Candidate full-log SHA256:
`20e866a227b6adf84fd304b4807b1c11a398b49f8f87d012aacd09ecee6007c1`.
Integration full-log SHA256:
`56d2c2b228b34fb4ae12ae8cee0f4fc63fc41c55542dc3eb84e4c76ffb4477de`.

The source correction is complete. Exact-head protected CI and a normal main
merge remain delivery gates, with identities recorded in the delivery PR. New
signed artifacts and fresh installed subscription acceptance remain separate;
this correction used zero provider invocations and does not close the stopped
rc.11 campaign or establish new live acceptance.

Last verified: 2026-10-30 UTC.

## Integration provenance

Frozen source `2f75d429c87b3b48c946832ff9c73748abf94efe` was committed only
after its complete gate passed. Its normal merge into main's documentation head
`b2f63b54974fe48f41c0ed3d2becea9c25157b8f` preserves candidate ancestry and
main's newer dependencies. The intervening main advancement changed four Markdown
files only. Memory resolution retains the current rc.11 evidence and new rc.12 row.
The actual merge reproduces all 857 tested non-Markdown inputs exactly.
Required exact-head CI and the normal protected merge are recorded in the delivery
PR; signing and fresh installed live acceptance remain separate.
