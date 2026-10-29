# rc.10 native authentication repair and fresh live qualification

- Status: authentication restored; fresh qualification stopped at RC10-SUB-02.
- Owner: Joshua Myers; operator: Codex; date: 2026-10-29 UTC.
- Exact application: signed immutable rc.10, source
  `9ffd540674cc322857c05f09bcaf8dc816b3ff64`, storage epoch 2, macOS arm64.
- Parent: [signed qualification review](RC10_QUALIFICATION_REVIEW.md).

## Objective, authority and guidance

The owner explicitly requested native Claude authentication repair, then fresh
live qualification. Preserve both earlier failed campaigns, conservative usage,
user credentials, published bytes and the exact source/tag. Use repository
AGENTS/CONTRIBUTING, the production-template bounded verification guide/loop,
work-note/threat-model templates and the existing declared installed matrix.
Risk is credential custody, subscription usage and workspace/state integrity.
This is owner-operated engineering qualification, not independent security review
or a sampling artifact. No provider payloads or credentials are committed.

Native authentication stays entirely with Claude. No credential cache, keychain
value or bearer token was read or copied by the harness. No API key, fallback,
credit purchase, client/model substitution or configuration wipe was used.

One fresh campaign was authorized with separate synthetic workspaces, session IDs,
stores, staging and usage roots. Maximum 14 native invocations per store/28 total,
one-hour authorizations, 90-minute controller ceiling, 60-second native deadlines,
8,192 native-reported output tokens, 16,000-byte text, 128,000-byte canonical input,
600-second coding walls and zero correction cycles. Native billing/internal
retries remain unverified; invocation limits are not dollar caps. Stop globally
on the first unplanned failure; no automatic retry, reset, renewal or replay.

Acceptance remains chat/linked steering/inspection refusal, passive cold resume
and contextual follow-up; ten-role provider-diverse coding with source-only
integration and unchanged protected tests/sentinel; four armed lease-bound worker
cleanups per store; passive post-coding resume; deliberate owned cancellation and
uncertain-scope refusal without replay. Both stores must pass for full acceptance.

## Authentication repair and fresh dispatch

The pinned Claude Code 2.1.283 reported signed out both inside and outside the
sandbox. Its native `auth login --claudeai` flow completed successfully after the
owner signed in through the browser. Native status then reported `claude.ai`,
first-party authentication. No inference was used to diagnose or repair login.

A separate installation reverified the enrolled-key metadata, archive/bootstrap
and exact native executable from the existing signed publication. Updates were
disabled in this private root. Installed readiness passed for Codex 0.163.0 and
Claude Code 2.1.283, with provider API keys absent. The controller repeated both
readiness checks immediately before minting fresh one-hour scopes.

The fresh campaign began at `2026-10-29T20:06:09Z`. Its preserved harness differs
from the earlier harness only in its evidence root; campaign scripts were hashed
before authorization and remained unchanged. The declared Sol/Terra/Sonnet/Astra
profile and immutable offline image remained exact. Prior rc.10 and rc.9 evidence
was fingerprinted before dispatch and verified unchanged afterward.

## Results and RC10-SUB-02

| Boundary | Observed result |
|---|---|
| Native Claude authentication | Restored; both plan and implementation Anthropic critic calls completed successfully |
| Snapshot conversation | Chat, linked queued steering, inspection refusal, passive cold resume and contextual marker recovery passed |
| Coding plan | Creator, both independent critics, judge and exact creator approval completed |
| Candidate | Child produced a source-only addition implementation; actual isolated verification reported passed |
| Implementation review | OpenAI critic requested concrete test execution evidence; Anthropic accepted; judge requested revision |
| Integration | Not started; workspace Git head/status/files, protected tests and sentinel unchanged |
| Guardian | Both actual baseline/candidate workers armed and produced lease-bound removal receipts; Docker independently confirmed both exact container IDs absent |
| Usage | Snapshot: 12 reserved/dispatched/completed calls, including nine coding-role calls. SQLite: zero |
| Stop/recovery | Zero correction cycles exhausted after the judge's revision. Operation retained as uncertain; no retry, replay, replacement scope or usage refund/reset |
| Remaining cases | Coding acceptance/integration, post-coding resume, deliberate cancellation and all SQLite live cases unrun |

RC10-SUB-02 is a review-evidence gap. The frozen
[CodingVerification contract](../src/mos_eisley/coding_child.py) exposes source/test
hashes, a pass boolean and an output hash. The
[worker](../src/mos_eisley/run/coding_child_worker.py) checks execution completion,
test-file identity, positive test count, zero skips and unchanged files internally,
but those concrete execution details are not carried into the
[live implementation review packet](../src/mos_eisley/conversation_live_coding.py).
The critic and judge requested executed test files/results and output size before
integration. This is not another authentication failure. The recorded candidate
pass is not sufficient to relabel the rejected live workflow as accepted.

Do not edit the model outputs, waive the findings, weaken the rubric, or run a new
scope to seek a different decision. No product correction was made under this
immutable tag. No post-failure resume was attempted or claimed as passing.

## Evidence, disposition and handoff

Private records remain in the integration worktree's
`.work/rc10-evidence/live-auth-refresh-1/` and `.work/rc10-auth-refresh/`.
Read-only closeout verified exact counters, two completed Anthropic calls, nine
coding results, the review decisions, unchanged harness inputs, no integration,
two armed/lease-bound cleanups, and unchanged original rc.9/rc.10 evidence.

| Record | SHA256 |
|---|---|
| Fresh closeout review | `9ae5573eab2f586aa47fe1efe6d1bf4915d5e7bdc8a8f9f6e1a63acf27b36fa7` |
| Stopped controller | `0c9bdbbbcbc6470632d8a0eb499d0592af52e73b40dec45e2f89fb332e2c0ca4` |
| Fresh campaign start | `83792734aa1f08e5ed39524fe4bbe1a1e6fc6f61b4ec49cb1decf6e0c55edc1e` |

RC10-SUB-01's authentication cause is resolved; its failed evidence and uncertain
usage remain historical. Full live-workflow acceptance remains incomplete due to
RC10-SUB-02. The next bounded implementation is a source/test-bound execution
receipt carrying the concrete test-completion details and bounded output evidence
into the review packet, followed by focused/source/wheel gates and a new signed
candidate with affected qualification. Do not alter or replace published rc.10.

This documentation-only follow-up uses relative-link/hash checks and
`git diff --check`; runtime/test inputs remain unchanged. The four-target signed
unpaid distribution acceptance remains passed. Live qualification here covers
macOS arm64 only; conversational `/review`, full v1 and existing platform/provider
activation gates remain separate.
