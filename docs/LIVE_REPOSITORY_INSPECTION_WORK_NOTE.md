# Work Note: live repository inspection

- Status: offline implementation verified; owner implementation acceptance satisfied
- Owner: Joshua Myers (accountable review); Codex (implementation)
- Started (UTC): 2026-10-04
- Verified (UTC): 2026-10-05
- Related plan: [§16 live conversation](mos-eisley-plan.md), [TUI guide](CONVERSATION_TUI.md)
- Selected guidance: [Python Engineering Guide](PYTHON_ENGINEERING_GUIDE.md), [Agentic Verification Guide](AGENTIC_VERIFICATION_GUIDE.md), [verification loop template](../templates/AGENTIC_VERIFICATION_LOOP.md), [threat model template](../templates/THREAT_MODEL.md), [adversarial playbook](ADVERSARIAL_REVIEW_PLAYBOOK.md), and [review template](../templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md).

## Objective and completion evidence

- Outcome: an explicitly authorized live `/inspect ` turn can list, search, and read bounded selected-workspace content and return source references.
- Invariants: ordinary live turns remain tool-free; session opt-in and an explicit per-turn command are both required; pasted or literal command text grants no authority; no path escape, symlink traversal, command or write tools; every provider response reserves under the separately selected policy and shared ledger before dispatch.
- Risk class: high, because repository contents cross a provider boundary and a tool turn may use more than one paid response.
- Evidence: offline reader, controller, provider-adapter and spending tests; strict typing/lint; one combined `make check` before publication. No credentialed call is part of this task.
- Resource ceiling: five provider responses and six read calls per inspection turn; no live provider spend during engineering verification.
- Stopping rule: fail closed on a blocking boundary defect; end verification after focused checks and the full gate pass, leaving accountable owner review separate.

## Context retrieved

[Repository agreement](../AGENTS.md), [project brief](../PROJECT_BRIEF.md), [project memory](../PROJECT_MEMORY.md), [v1 plan](mos-eisley-plan.md), [live TUI guide](CONVERSATION_TUI.md), [live chat threat model](CONVERSATION_LIVE_CHAT_THREAT_MODEL.md), and relevant controller, provider, spending, path-reader, and test code.

## Handoff

- Candidate worktree: `feat/live-repository-inspection`, based on `origin/main` at `5a6be4e`.
- Joshua Myers accepted the exact implementation scope conditional on gates passing, 2026-10-04. The condition is satisfied by the completed gate. Credentialed validation, live spend, merge, and release remain separate.

## Implementation and adversarial checks

The controller persists explicit inspection authority separately from message text. Launch/resume identity includes the repository profile; the TUI shows that profile and inspection turns. The runtime constructs only the fixed repository dispatcher, pins the workspace per launch, and repeats admission for each model response. No dependency was added.

Checks challenged unsafe paths, symlink parents and leaves, special files, UTF-8/result bounds, changing file bytes, workspace substitution during counting, switched workspace confinement, hostile instructions, altered tool schemas, and aggregate cap exhaustion. Literal-prefix authority, nullable SDK reasoning fields, result-label overhead and invalid source-line references were corrected during implementation. These are one agent's checks, not independent owner review.

- Final focused command: `uv run --frozen python -m unittest tests.test_live_repository_read tests.test_conversation_live_chat tests.test_openai_spend -q` — **39 passed**.
- Final static command: `make lint typecheck` — lint/format passed; strict typing **0 errors, 0 warnings**.
- Combined `make check` — **passed, exit 0**. Source suite: **2,737 run, 4 skipped**; installed-wheel smoke: **1,995 passed**. Lint, strict typing, coverage reporting, runtime-export verification and build completed. Skipped tests are not counted as passing qualification evidence. An earlier sandboxed run was interrupted because nested macOS Git isolation failed; it is not passing evidence. The successful combined gate ran outside the agent sandbox.
- During that combined source run, the SDK-history, result-label, source-line and private-directory corrections were made. The focused command above reran the affected paths after those corrections; final static checks and the installed-wheel smoke cover the resulting candidate.
- No credentialed requests, spend, merge, or release occurred.

Exact source/test scope SHA-256: `ed453675e12205d3eac17438f08602b0e3f51b3a802480d1c04195e99864b5a7`. See the [candidate inventory](LIVE_REPOSITORY_INSPECTION_CANDIDATE.json) and [owner review packet](LIVE_REPOSITORY_INSPECTION_OWNER_REVIEW.md).

Tested wheel: `mos_eisley-0.1.0-py3-none-any.whl`, SHA-256 `651e4a080b313df95684e02b78e346fcd0c6ab2a1b8f248866ddb6ba17458d31`. The final code/test inventory still matches its accepted scope after documentation closeout.
