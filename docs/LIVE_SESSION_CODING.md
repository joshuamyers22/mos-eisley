# Connected live session coding

Explicit `/implement TEXT` can use a connected creator workflow when launched with
`--live-coding-selection PATH --allow-live-coding` and the existing live OpenAI
chat options. Ordinary chat and `/plan` retain their existing behavior. The
selection hash is part of saved session identity; resume requires the same
selection bytes, current pricing, ledger, credentials and execution image.

This is a source implementation candidate for the existing bounded
`pure_python_v1` execution profile. Source and unpaid Docker/Git fixtures are
engineering evidence; they do not qualify the new combined provider workflow,
release image or general repository coding. A separately budgeted exact-candidate
live demonstration and accountable review are required before release claims.

## User journey

The creator sees the admitted author context and selected source/test snapshot.
It writes a concrete plan, interfaces, acceptance criteria and additional
executable tests before any coding-child call. The controller freezes these
artifacts and executes baseline tests in the selected offline container.
Two distinct OpenAI/Anthropic critics review that package without author history;
the distinct judge receives the artifact and anonymous findings. The creator must
approve the exact package and accepted adjudication before the child is called.

The child receives only the explicit brief, owned source content/digests and any
previous candidate's correction evidence. Its tool-free response proposes complete
source replacements. The host validates ownership, before-content digests and the
pure-function policy; a separate offline Docker process executes the immutable
test package. Its verification brief retains the existing unpaid fixture execution
profile; live model identity and spending are separately pinned by the selection
and each role's host transport receipt. Failed tests or implementation review can
trigger at most the selected correction count, with exactly the same plan/tests
and base revision.
Creator refusal of integration also consumes this correction allowance.

A passing candidate needs critic/judge review and exact creator approval. The
trusted Git broker stages it in a private detached worktree, reruns the complete
frozen test package and performs a one-use fast-forward. The actual integrated
source is reread and tested in a fresh container before success is reported.
Creator tests stay in the private artifact package; repository tests are preserved.
The returned commit contains only approved source changes.

## Explicit operating selection

Prepare a `LiveCodingSelection` JSON file using the schema in
`src/mos_eisley/conversation_live_coding.py`. It binds:

- Exact absolute workspace, sorted existing tracked `source_paths` and `test_paths`.
  The source must fit the existing pure-function profile and the repository must
  pass the existing Git broker's clean-tree, size and configuration restrictions.
- Creator, child, two critics and judge routes, each with `provider`, `model`,
  exact `effort`, an absolute `spend_policy` path and `expected_policy_sha256`.
  Creator/child use OpenAI. Critics include both providers. Creator, each critic
  and judge must use distinct models; effort substitution is rejected.
- Existing `spend_ledger` and `expected_ledger_id`, private existing
  `artifacts_root`, private `staging_root` outside the workspace, absolute `git`
  and `docker` executables, and immutable `image_id`.
- Timezone-aware `valid_until`, whole-workflow `max_total_microusd`, byte ceilings,
  `correction_cycles` (0–2) and `wall_seconds` (30–1800).

Use the already-qualified component routes and freshly reviewed schema-2 pricing;
the new composition still needs its own qualification. The creator's model,
effort, policy hash, shared ledger and artifacts root must match live chat.
For example, select the existing OpenAI creator/child routes, an OpenAI critic,
Sonnet critic and Opus judge without silently choosing or downgrading models.
Do not put credentials in the selection or repository. Provider keys are read from
`OPENAI_API_KEY` and `ANTHROPIC_API_KEY` by the host.

```sh
mos chat --live-openai --allow-data-transfer \
  --spend-policy /private/path/creator-policy.json \
  --spend-ledger /private/path/spending.sqlite \
  --live-artifacts /private/path/artifacts \
  --live-effort high \
  --live-coding-selection /private/path/coding-selection.json \
  --allow-live-coding
```

Then type `/implement TEXT` in the TUI or plain terminal. Pasted or explicitly
literal text does not grant implementation authority. A bare launch or ordinary
message sends no coding request. The connection currently requires an ordinary
session: a fork, durable goal or separate task-profile budget is rejected before
coding dispatch rather than resetting or bypassing that budget.

## Failure and evidence

Every role call conservatively charges its full output and worst-case monetary
allowance against the workflow before awaiting. Existing spending transports
atomically reserve and settle each exact request in the shared ledger. All roles,
reviews, approvals and corrections count. There are no SDK retries, automatic
refunds or learned routing. Selection/pricing expiry, changed source, lost durable
state or newly queued steering stops subsequent work.

Private `coding-NNNN` attempt directories retain the frozen brief, request hashes,
model artifacts, spend receipts, candidate test receipts, handoff and integration
markers. Existing attempt directories refuse replay. Cancellation preserves held
exposure and the session records a cancelled attempt. Cold resume does not retry
it. After a lost integration acknowledgement, inspect `integration-started.json`
and `applied-commit.json` against current Git state; a disappearing diff or model
completion never proves success. There is no automatic recovery integration.

The unpaid Docker/Git smoke command is:

```sh
uv run --frozen python tools/smoke_live_session_coding.py \
  --docker /absolute/path/to/docker --image-id sha256:EXACT_IMAGE_ID
```

Production-template guidance and verification outcomes are tracked in
[the work note](LIVE_SESSION_CODING_WORK_NOTE.md).
