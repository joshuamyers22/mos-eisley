# rc.12 signed qualification

- Status: closed at the declared stopping rule; signed distribution passed,
  installed live qualification incomplete (RC12-SUB-01). Owner Joshua Myers;
  operator Codex. Started and reviewed 2026-10-31 UTC.
- Frozen application: `2f75d429c87b3b48c946832ff9c73748abf94efe`, rc.12,
  storage epoch 2. PR #344 merged normally after all 13 required checks passed.
- Protected exact-tag release run: `41149254988`, attempt 1. Existing release
  and failed campaign artifacts remain immutable; no tag retargeting.

## Contract, guidance and boundaries

The owner requested signed rc.12 qualification. Apply the repository bounded
verification guide/loop, work-note and threat-model templates, release preparation
and installed/upgrade runbooks. Verify enrolled-key custody, exact source/tag/run,
all four macOS/Linux target hashes, signed installed matrices on both stores,
historical predecessors and actual published rc.11 upgrade/rollback. Review
evidence before any operator publication approval. Owner/operator overlap does
not establish independent security approval.

The frozen release workflow qualifies seven predecessors through rc.10. A
separate host-only workflow admits immutable rc.11 release `429106203`, source
`4d927cea23ff18f6aa9d231f7c342ee8e2420c84`, and pins the exact rc.12 protected
run, tag, source, workflow and attempt. It requires successful preparation and
all four signed jobs. Default enrolled signature, archive/bootstrap, state,
recovery and rollback checks remain strict. This does not change the candidate.

Threats: substitution of unsigned artifacts or another run, stale approvals,
credential exposure, replay of uncertain work, review bypass and unbounded spend.
Keep signing keys in protected custody, native credentials client-owned, artifact
and approval observations fresh, and all private capabilities/raw responses out
of Git. Publication remains an accountable owner action; record actual external
publication if it occurs rather than claiming it was withheld.

## Budget and stopping rules

One host-control batch: focused predecessor/publication contracts, full
`make check` within four hours and required CI before normal merge. Four actual
rc.11 journeys use no provider calls. Build a fresh immutable worker image from
the exact candidate; prior images do not establish new-source identity.

After signed evidence review and fresh installed native readiness, run one fresh
subscription campaign: 14 invocations/store, 28 total, one-hour grants, 90-minute
global ceiling, 60-second native deadlines, 8192 reported output tokens, 16000
text bytes, 128000 canonical input bytes, 600-second coding walls and zero
correction cycles. Preserve the existing exact Codex/Claude model/client profile,
actual HOME and any existing CODEX_HOME selection. No API fallback, added credits,
model substitution, renewed authorization, automatic retry or failed-session replay.
Native billing/internal retries remain unverified. Stop globally on the first
unplanned signature, provider, protocol, test, review, integration or cleanup
failure; retain all evidence and unused capacity. No broad v1 acceptance follows.

## Host-control verification

Focused distribution/publication contracts passed 42/17 cases. Ruff/format and
strict Pyright passed. Full source coverage passed 3,896 cases in 2,826.425s
(17 skips), at 86%; export verification and build passed. The initial installed
wheel run was nonpassing: 9 failures, 173 errors, 13 skips. Most errors reported
missing SDK-version metadata; a startup case also crossed a wall-clock pause
while its monotonic elapsed time remained short. The precise environment cause
is unestablished; no production guard, test or deadline was changed.

A fresh private temporary environment reran the complete failed `make smoke`
stage only: 2,880 cases in 2011.394s, 13 skips, exit zero. All required
quality stages therefore pass against the same 858 input names/content hashes.
The original `make check` exit 2 and logs remain unchanged, rather than being
reported as a successful single invocation. No passed source tests were repeated.
Original log SHA256: `260b83b76694e2fca6bb9288836c7f4d92fd1f9e4669908e03a194e9beb0ada5`.
Wheel retry log SHA256: `e9a9d70834c7560336221551780cd77453a3570642271cd804b507ca7aabe439`.

Protected preparation and all four signed rc.12 jobs passed; the independent
base review admits 38 reports and 55 official candidate assets. The actual
signed macOS arm64 guardian/offline-worker probe also passed, including its
bound receipt, invalid-lease refusals and exact container removal. Private rc.12
installation and both pinned native readiness checks passed without inference.
PR #345 passed all 17 required checks and merged normally as
`a4b296203178fcecd733cc2118b3f994ded767b8`, preserving the exact tested tree.
Additional run `41228212608`, attempt 1, passed all four actual rc.11 upgrade,
rollback and recovery journeys. Combined independent review admits 42 reports.
The owner published immutable release `430032833` at `2026-10-31T15:57:38Z`,
before the additional/live review; all 55 public asset identities and immutable
attestation match. No operator preparation/publication approval was submitted.

The single fresh signed macOS arm64 subscription campaign passed snapshot chat,
steering, cold resume, context, plan review and candidate tests. Claude's
implementation critic exceeded the unchanged 60-second native deadline:
11 dispatches, 10 completions, one uncertain call; SQLite zero, no integration.
Global stop preserved the unused 17-call capacity. Read-only audit confirmed
unchanged workspace/protected files, scripts and all prior campaigns, and exact
removal of both live worker containers. No resume, retry or replacement scope
was attempted. See the [qualification review](RC12_QUALIFICATION_REVIEW.md) for
hashes, scope, finding and remaining work. The [offline diagnosis](RC12_CLAUDE_TIMEOUT_DIAGNOSIS.md)
confirms native-exchange timeout ambiguity and missing progress receipts. Next:
bounded redacted diagnostics before a separately bounded fresh campaign. Full v1 acceptance remains
open. Closeout changes documentation only; applicable checks are relative links,
artifact identities and `git diff --check`.
