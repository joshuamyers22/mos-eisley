# Agentic Verification Loop: live read-only review qualification

## Objective and authority

- Requirement, issue, or project-brief link: `docs/ROADMAP.md` G2,
  `docs/REVIEW_CAMPAIGN_CEREMONY.md`, and `docs/REVIEW_LAUNCH_ADMISSION.md`
- User journey or operational outcome: qualify and admit one exact
  bounded critic/judge review without turning fixtures, local signatures, or prior
  calibration evidence into broader provider or routing authority.
- Invariants and non-goals: three precommitted fixed attempts; phase/local approvals;
  one consistent Joshua Myers signer with explicit self-review risk acceptance; exact current
  guidance/runtime/spending; complete cleanup and evidence; no retries, automatic
  release, scoring, provider-authorship claim, public CLI, or global activation.
- Risk class: high-risk
- Implementation owner: Josh Myers
- Verifier or accountable approver, if required: Joshua Myers as the single accountable
  operator under ADR-0005; no independent human approval is claimed
- Commit/revision and starting worktree state: GitHub `main`
  `fa0faafb6f29421e46429001be3932b614f392f0`; guidance branch created from that ref

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Exact qualified review profile | Blocking | Fresh campaign review and launch-conformance reconstruction | All three slots qualify and launch role/quorum/runtime scope matches exactly |
| Correctness and failure handling | Blocking | Fixed-slot failures, timeout/cancellation cleanup, no-retry receipts, ledger and crash inspection | Missing/failed/uncertain evidence stops later work and never becomes success |
| Security/privacy/data integrity | Blocking | Single enrolled key/custody record, explicit self-review acknowledgement, signed decisions, private permissions, exact hashes, secret/data review | Credential and prompt access occurs only after all current gates; no key/bearer/raw error is retained |
| Financial authority | Blocking | Dedicated ledgers, conservative full allowances, exact settlement/uncertain state, separate launch ledger | No unreserved call, double reservation, automatic release, or campaign-ledger reuse |
| Maintainability/operability | High | Current policies, immutable SDK/image, bounded deadlines, recovery and cleanup evidence | Every operation is inspectable and revocable before the next provider boundary |

## Budget and stopping rules

- Maximum iterations: three fixed conformance attempts plus one exact launch decision;
  failed or missing fixed slots are not replaced
- Elapsed-time or review window: bounded by the sealed campaign, phase, observation,
  and launch-policy expiries
- Compute/cost ceiling, if material: owner-approved aggregate maximum USD 5.00
  (`5,000,000` micro-USD) across qualification and launch; the exact reviewed bundle
  and separate launch envelope must fit within it
- Pass rule: all blocking rubric rows pass through fresh reconstruction and the
  consistent schema-2 Joshua Myers signature; production launch remains unavailable
  without the final decision
- Diminishing-return rule: the fixed campaign ends after its three slots; no additional
  attempts are authorized to improve the narrative
- Escalation/domain-input trigger: evidence is ambiguous, a ledger is nonempty/blocked,
  policy expires, runtime differs,
  or remote receipt/invoice state is uncertain
- Rollback or abort condition: any substituted input, reused path/ledger, credential
  access before current gates, missing cleanup, duplicate dispatch, or broader authority
  claim

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Template and repository survey only | Current upstream template and GitHub `main` state | Blocking external custody and paid-run authority are absent | Stop before credential/spend/provider actions | Documentation/source inspection only |
| 2 | Explicit schema-2 single-operator contract | ADR-0005, threat review, schema/mode validators, positive full-path and mixed-mode tests | Independent-human-review control is intentionally removed; other gates remain | Record self-review risk, preserve schema-1 default, reject mixed modes | Focused single-operator tests pass |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| Q-001 | `REVIEW_LAUNCH_ADMISSION.md`: production custody, live assessment, and decision remain outstanding | Local fixture evidence cannot authorize live review | Blocking | Accepted; requires real operational inputs, not a code workaround | Retained and signed campaign and launch evidence | Josh Myers |
| Q-002 | No public live-launch CLI by design | A casual command cannot safely begin the review | High | Accepted; use the owning library ceremony until a separately reviewed product boundary exists | Exact admitted owning flow and retained evidence | Josh Myers |
| Q-003 | The owner requires Joshua Myers to hold every human role | No independent human can detect Joshua's mistaken or malicious self-approval | Accepted high risk | ADR-0005 explicitly changes the contract; schema 2 requires one shared signer and a signed self-review-risk assertion, while schema 1 remains separated | Positive full-path test, mixed-mode rejection, and no independence assertion in schema-2 decision | Joshua Myers |

## Exit

- Stop reason: contract change passed focused verification; live execution remains
  pending operational inputs and is approved only up to USD 5.00
- Rubric result and blocking findings: Q-003 is accepted by the accountable owner;
  Q-001 remains open until real live evidence exists, and no live claim is made
- Full quality-gate command and result: `make check` passed: Ruff and Pyright passed;
  2,437 source tests passed with four skips and 89% coverage; export verification,
  sdist/wheel builds, and 1,839 installed-wheel tests passed
- Production-like replay/fault/rollback evidence, if applicable: existing synthetic and
  Docker coverage is documented in the feature guides; it is not production evidence
- Remaining uncertainty, owners, and dates: Joshua Myers must supply one real public
  signing key, credential custody, runtime image, funded ledgers, and provider-account
  data policy before execution
- Human/domain approval, if required: Joshua Myers explicitly approved single-operator
  governance and the USD 5.00 aggregate ceiling on 2026-09-19
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: latest delivery
  state and template-use rule recorded in `PROJECT_MEMORY.md`

## Diagnostic resource accounting (optional)

- Iterations and elapsed time: one source-survey pass and two contract-review passes
- Aggregate tokens/cost, when policy permits: zero provider cost
- Accepted versus rejected findings: one accepted operational blocker and one accepted
  high governance risk; three contract risks resolved
- Escaped defects or regressions discovered later: unknown
