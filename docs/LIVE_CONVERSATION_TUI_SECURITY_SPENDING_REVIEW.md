# Live conversation TUI: security and spending review

- Review date: 2026-10-01
- Candidate: PR #252, code commit `c29c1f5`; original reviewed code was `caafb300ab7dc81ef7f22c9e7e0a45a3e025bc8b`
- Scope: `mos chat --live-openai` and exact-session resume; no provider call or release authorization
- Reviewer: Codex engineering assessment for Joshua Myers's accountable decision
- Status: corrected candidate verified; owner decision pending
- Selected guidance: `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
  `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`, and `templates/THREAT_MODEL.md`

## Decision proposal

Approve the corrected implementation boundary for a separately authorized,
bounded live validation. One spending defect was found and corrected: the
original live launch accepted schema-1 policies, which cannot price cache writes
conservatively. The CLI and runtime now require schema 2 before dispatch. No
blocking defect remains in the reviewed path. This decision would not approve a
particular price policy, ledger ceiling, provider call, G2 campaign, merge, or
release.

## Boundary trace and evidence

| Question | Observed control | Evidence |
| --- | --- | --- |
| Can a recorded session silently become live? | Live mode requires explicit transfer and spend flags. The saved mode and model, effort, policy hash, ledger ID, output cap and artifact root must match on resume. | `conversation_cli.py`, `conversation_state.py`, `test_conversation_live_chat.py` |
| Can a turn send twice after cancellation or crash? | The controller saves `running` and consumes its attempt before dispatch. Resume interrupts running work; an attempt uses an exclusive artifact directory and cannot be reused. | `conversation.py`, `conversation_live_chat.py`, `test_conversation_live_chat.py` |
| Can generation bypass the spending hold? | The CLI and runtime require a schema-2 policy. The transport counts tokens, validates the current per-call policy, writes a private reservation, and atomically reserves against the shared ledger before `create_response`. A duplicate entry or exhausted/blocked ledger rejects generation. | `conversation_cli.py`, `conversation_live_chat.py`, `openai_spend.py`, `spend_ledger.py`, spending tests |
| Can the provider invoke local tools or redirect the key? | Live chat supplies `NoToolsDispatcher` and one iteration. The SDK uses the fixed OpenAI endpoint, disables retries, redirects and environment proxies, and bounds decoded responses. | `conversation_live_chat.py`, `openai_live.py`, `openai_http.py` |
| Are credentials and artifacts scoped? | The key is read from the environment at launch and is not saved in session state or ledger. The selected artifact root must be an existing owner-only directory; attempt directories are exclusive and owner-only. | `conversation_cli.py`, `conversation_live_chat.py`, `store.py` |

PR #252's source, package, container, quality and secret-scanning checks were
green for the original candidate when checked on 2026-10-01. A focused local run of
`uv run --frozen python -m unittest tests.test_conversation_live_chat tests.test_openai_spend tests.test_spend_ledger`
passed 42 tests after the schema-2 correction. The original implementation work
note records its earlier quality gate and focused checks. A sandboxed full run
reached all 2,642 tests but failed 31 unrelated MCP HTTP fixtures because
loopback socket binding was denied. The elevated `make check` on code commit
`c29c1f5` passed: lint, formatting, typing, 2,642 source tests (four skips),
86% branch-inclusive coverage, build, and 1,918 installed-wheel smoke tests.

## Scope limits for the owner

- The token-count request transfers admitted conversation text **before** the
  generation reservation. The ledger bounds generation exposure; it does not
  establish a charge bound for the token-count endpoint. The launch's explicit
  data-transfer opt-in covers both requests.
- Spending rates and the aggregate cap are operator supplied. The code cannot
  verify that a selected policy reflects current provider pricing or that calls
  made outside the selected ledger fit its ceiling. The earlier G2 campaign cap
  does not authorize TUI calls.
- A cancelled or interrupted generation may have completed remotely. Its full
  reserved amount remains held or uncertain until separately reconciled; neither
  the controller nor resume automatically retries it.
- The local owner has trusted access to session, policy, ledger and artifact files.
  Their hashes and file modes do not defend against that same owner substituting
  files. This is the documented single-owner host boundary.
- This assessment used source inspection and offline tests. An exact-candidate
  credentialed TUI turn with a reviewed short-lived policy and approved ledger
  remains necessary before claiming live operation.

## Owner decision

Joshua Myers accepted the original implementation assessment on 2026-10-01.
Because the schema-2 guard changes the reviewed code, acceptance of the corrected
candidate is pending. Acceptance covers the implementation controls above only.
