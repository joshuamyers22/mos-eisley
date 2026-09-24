# Agentic Verification Loop: corrected cleanup-boundary qualification

## Objective and authority

- Requirement: reassess G2 after a wholly fresh formal three-slot production
  qualification of the terminal cleanup boundary correction at exact source commit
  `3b32f1426ce067696307c3ea4a96ef61ea583411`.
- Operational outcome: determine whether the exact commit and production image meet
  the G2 live read-only review exit without treating qualification as launch authority.
- Invariants and non-goals: retain every fixed slot and failure, require threshold-two
  quorum and the conditional judge, preserve exact accounting and cleanup, make no
  retry, and do not infer provider authorship, invoice reconciliation, routing,
  launch, or broader activation.
- Risk class: high-risk authorization, private-data transfer, and financial evidence.
- Owner and accountable reviewer: Joshua Myers under ADR-0005 single-operator mode;
  no independent human review is claimed.
- Starting state: clean `feat/production-template-guidance` worktree at `3b32f14`.
- Selected guides: `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/WORK_NOTE.md`, the existing
  `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_THREAT_MODEL.md`, and
  `docs/REVIEW_CAMPAIGN_CEREMONY.md`. These guides derive from the pinned production
  template recorded in `AGENTS.md`.

## Rubric and stopping rules

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Exact qualification profile | blocking | Sealed bundle, three signed observations, fresh campaign reconstruction | All three precommitted slots qualify against one exact commit, image, SDK, role and quorum profile |
| Review outcome | blocking for this corrected subject | Retained critic outcomes and judge verdicts | Every slot reaches an `accept` verdict with no upheld finding or required change |
| Authorization and privacy | blocking | Exact phase/local approvals, private permissions and transfer controls | No credential or provider use before its gate; `store=false`, no tools, and no secret copied into Git |
| Accounting and cleanup | blocking | Dedicated ledger reconstruction and worker lifecycles | Zero unresolved entries; all workers removed; no retry or substituted slot |
| Authority scope | blocking | Acceptance denial fields and time-bounded policy window | Qualification is not represented as launch, provider authorship, billing reconciliation or reusable dispatch authority |

- Maximum live work: exactly three fixed slots, each with three critics and one
  conditional judge; no retry or replacement.
- Planned ceiling: 83,664 micro-USD per slot and 250,992 micro-USD aggregate, within
  the separately approved USD 5.00 owner ceiling.
- Window: campaign policy from `2026-09-24T00:56:11.506726Z` through
  `2026-09-24T01:26:11.506726Z`; every accepted result was evaluated inside it.
- Stop rule: stop on a missing slot, failed quorum, unresolved ledger entry, changed
  artifact, incomplete cleanup, or absent exact human gate.

## Exact campaign record

- Production image: Linux/arm64
  `sha256:3f67fa22ae6ede838269a292ad507e6441d6a5d084fbf5a2c6077ea125be8653`
- Runtime: Python 3.12.14, Mos Eisley 0.1.0, OpenAI SDK 3.11.0
- Campaign bundle:
  `62f23f3fbe16485a6153ee7942d6a419f55f57a853203530feeac626ec44e929`
- Campaign seal:
  `ab71fca34ea809910ae650f3d662fc878dcc9d73a687d3303000f3af14e703d2`
- Acceptance policy:
  `8a8973cd9217874752d4adf9b5ccf0f4c114684349c47a8f445e0442f51af0c3`
- Profile: three distinct `gpt-5.6-luna` low-effort critics per slot,
  threshold two, one conditional judge, strict structured output, content-bound
  citations, `store=false`, no tools, and zero automatic retries.

An earlier inert host-construction attempt failed before bundle creation, sealing,
credential access, reservation, worker creation, or provider use. Its private partial
record remains retained and contributes no slot or qualification evidence. The
campaign above was prepared afresh after that offline harness correction.

## Results

| Slot | Review-result SHA-256 | Critic outcomes | Verdict | Findings / changes | Charge |
|---:|---|---|---|---:|---:|
| 1 | `3f6f7f54aa872b6bd6c32ae196f640b32a16bdac0420fefc8fb7d0ad47001ead` | 3 completed | accept | 0 / 0 | 11,644 micro-USD |
| 2 | `866792a2f195bac6ce8e7b3879c8d9041646feb180243e073e1129ccf388e35f` | 2 completed; 1 `invalid_evidence` | accept | 0 / 0 | 10,382 micro-USD |
| 3 | `a7bf9a30c4c11cce3ead85b70ca703f8f7c91930cc8587db0e632766b712fca3` | 3 completed | accept | 0 / 0 | 10,200 micro-USD |

Slot 2 preserved the invalid critic rather than retrying or silently treating it as
valid. Its two valid empty critiques met the precommitted threshold-two quorum, and
the judge accepted with no upheld finding. This is an exercised failure-tolerance
path, not three-success evidence for that slot.

The exact post-result observation confirmations were, in slot order,
`506bcac25b7670ab125bc14c2a910c0860b1a597df8a97200e6049a6d1341cb4`,
`4208985be198e6f7bd767bfc13e278ba661595a2212171bcc0b8069d65e0b291`,
and `28d38af3389b098015cc900b83a596a36b5ca720965f86398f080291bacaa91b`.
The signed observation hashes authenticated by the final result are
`b234761b449d462e4d9fb53dcd34ae617ab9af46a848c81b89eb171a304db769`,
`51722c507ab941ee73b8c086efeae27d7039f72e68eed84115bed7eb69497f17`,
and `9f18040186401fe0e436f7c2972bd9b52a254e7773ba4356b9b94fa9a57003e9`.

The canonical campaign-evidence SHA-256 is
`fde095a16c20e4054567984d7b13bd663b7ac5a81f5301088a36726619962c8a`.
The retained campaign-result SHA-256 is
`0a276558ef24b8233c154c64d136aab47629ef632b4bfa26a11f9d4e7c6a37df`.
It records `accepted` with three qualifying attempts while explicitly leaving live
activation, provider dispatch, retry, provider-authorship proof and billing
reconciliation false.

## Verification passes

| # | Evidence | Result | Decision |
|---:|---|---|---|
| 1 | Exact clean source commit and rebuilt image inspection | Source was clean at `3b32f14`; the pinned Linux/arm64 image matched the checkout and contained the expected runtime without source, tests, Git or build tools | Admit the exact image to a new campaign only |
| 2 | Bundle preview, independent replay and seal-byte hashes | Three empty dedicated ledgers, distinct fixed slots, private paths, exact commit/image/profile and 250,992-micro-USD maximum matched; raw and canonical bundle hashes agreed | Seal the exact bundle; do not reuse prior campaigns |
| 3 | Per-phase gates and retained slot inspection | Every critic and judge phase required exact human scope/preview approval; every result required exact observation confirmation | Count only the explicitly observed fixed results |
| 4 | Fresh campaign reconstruction | The repository `review-campaign-review` verifier returned `accepted`, three qualifying attempts and the three expected signed-observation hashes | Qualification evidence is internally consistent and authenticated under single-operator mode |
| 5 | Accounting, permissions and cleanup | 32,226 micro-USD settled across 15 terminal entries; every ledger is unblocked with zero unresolved entries; files are mode 0600 below a mode-0700 root; all 12 lifecycle records end `removed`, and Docker lists none of their IDs | Accounting and cleanup pass; invoice finality remains outside the claim |
| 6 | G2 plan and launch-boundary reassessment | Plan §26.4 requires authorized credentialed conformance and a frozen brief through live critics/judge with quorum, bounded spend, cancellation controls and evidence; the exact campaign plus existing cancellation/container gates satisfy that exit | Mark G2 qualification complete, while keeping production launch behind its separate current decision and fresh authority |
| 7 | Documentation-only repository verification | Ruff and Pyright passed; the 2,431-test source run had only 31 sandbox loopback-bind errors and four skips; the isolated MCP family passed all 68 tests with four skips when granted localhost permission | Accept the documentation batch without rebuilding the unchanged qualified image |

## Finding disposition

| ID | Evidence | Severity | Disposition | Required action |
|---|---|---|---|---|
| CQ-001 | Slot 2 retained one `invalid_evidence` critic | non-blocking under the sealed threshold-two policy | Accepted as transparent fault evidence; two other critics completed with no findings, the judge accepted, no retry occurred, and campaign reconstruction qualified the slot | Retain the error; do not rewrite or claim three valid critics |
| CQ-002 | One operator held every human role | accepted high risk | ADR-0005 explicitly records self-review and provides no independence claim | Reassess before broader activation or when an independent reviewer is available |
| CQ-003 | Provider authorship and billing remain false | outside qualification | Local evidence authenticates the operator and retained runtime chain, not a provider identity or invoice | Reconcile separately if an invoice claim is needed |
| CQ-004 | No production launch decision was created | blocking for launch, not G2 qualification | The campaign closes qualification but its denial fields and finite window grant no launch or reusable dispatch authority | Require a wholly separate current launch ceremony before any target live call |

## G2 reassessment and exit

G2's concrete plan exit is satisfied for the live read-only review capability. The
exact corrected artifact completed three precommitted credentialed slots with
preserved quorum, bounded spending, signed observations, fresh evidence
reconstruction, retained artifacts and complete cleanup. All three content verdicts
are `accept`, with no upheld finding or required change. The historical Q-011 gap—a
standalone success without three committed slots—is closed by this campaign.

This is not a production launch. The campaign's finite window and acceptance record
cannot by themselves become launch authority. `ReviewLaunchAdmissionInputs`, a
separate launch ledger, a current signed launch decision accepting ADR-0005 self-review
risk, exact target phase approvals and all ordinary gates remain necessary before any
future target call. This work will not reuse the campaign for dispatch. No further
live qualification call is required or authorized by this reassessment.

- Stop reason: passed the G2 qualification rubric.
- Remaining blocking item: separately authorized production launch admission, only
  if and when the owner chooses to launch a target review.
- Next non-live project work: proceed to G3's open real-label, trust-policy,
  holdout-custody and independent statistical-review inputs, or prepare an offline
  launch proposal without dispatch authority.
