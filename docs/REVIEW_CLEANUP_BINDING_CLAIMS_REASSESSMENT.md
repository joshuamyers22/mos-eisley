# Agentic Verification Loop: cleanup binding claims reassessment

## Objective and authority

- Requirement: reassess the mutable-binding, campaign-ID and terminal-window claims
  from the formal campaign at source commit
  `326dafef08a58012499187392fc5b04a3056624e` before another live call.
- Operational outcome: distinguish executable defects from correlated reviewer
  misunderstandings and close the remaining offline regression-evidence gap.
- Invariants and non-goals: terminal cleanup must remain bound to the exact sealed
  slot and its original window; no retained campaign evidence is rewritten; no live
  call, retry, launch, qualification or spending authority is inferred.
- Risk class: material authorization, accounting and regression-evidence review.
- Owner and accountable reviewer: Joshua Myers.
- Starting state: clean `feat/production-template-guidance` worktree at `326dafe`.
- Selected guides: `templates/AGENTIC_VERIFICATION_LOOP.md`,
  `templates/THREAT_MODEL.md`, `templates/WORK_NOTE.md`,
  `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md` and
  `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`.

## Campaign evidence under review

The campaign evidence reconstruction accepted all three authenticated slots, settled
63,461 micro-USD locally, removed all 12 workers and retained zero unresolved ledger
entries. The three code verdicts were `revise`, `reject` and `reject`, so the subject
did not qualify. Acceptance authenticates the campaign execution and observations;
it does not make every source interpretation correct.

- Seal: `5f22b9fd678d9f800bacca3761f6bde1afe38cbfb6270cebf372a256b946b31d`
- Evidence: `6dd1d8cc23af777ed71919c036ac47a464453d85cdbebfc1c35f439518387625`
- Acceptance: `d0984daddca4d1422d6e6bc2187d33889c598e301710d4a268f015a303fa9161`
- Result files: `37b8188637b852d6f01cfe5f6f27cf1af20fbcd67eb064858ef05ec4cd8f58ca`,
  `73de3d1676b57e0a6684083690aa02e68e4a8f96fcd8cd33afd6ca03bcdd86e3`
  and `bc30bdceb4d7cdbfe2cb83e72108bf921e2e07913f179d78cccf37b175ed0681`.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Binding immutability | blocking if mutable | Base contract, binding fields, ownership copies and executable assignment probe | No supported caller can mutate the retained or exposed selection in place |
| Campaign identity | blocking if absent | Seal, bundle and binding schemas plus every seal read | One independently retained value identifies and authenticates the exact campaign bytes |
| Terminal seal recheck | blocking | Controller failure path and post-start tamper regressions | Changed sealed bytes preserve the judge hold at terminal cleanup |
| Terminal time window | blocking evidence requirement | Cleanup predicate and boundary regressions | Start before sealing or at/after the earliest committed expiry cannot retire the hold |

## Source trace and dispositions

### Mutable binding — rejected

`ReviewCampaignBinding` inherits `Contract`. `Contract` applies Pydantic
`ConfigDict(frozen=True, extra="forbid", strict=True)`, so assignment to
`campaign_directory`, `expected_seal_sha256` or `attempt_index` raises a
`frozen_instance` validation error. All three fields are scalar values, so the model
contains no nested mutable collection. The probe, admission and controller also each
take an owned canonical validation copy of the supplied binding. Returning the
retained frozen scalar model from `campaign_binding` therefore does not expose a
mutable authority object.

The critic quoted only the subclass field declarations and omitted the inherited
configuration. An offline assignment probe confirmed the exception and that the
original model remained byte-for-byte unchanged. `model_copy(update=...)` in tests
creates a different model; it does not mutate the retained instance.

### Campaign ID — rejected as a specification terminology error

No executable campaign contract defines a separate `campaign_id`. Campaign identity
is the independently retained `expected_seal_sha256`:

1. `read_campaign_seal` hashes the exact `seal.json` bytes and compares them with
   that independent pin.
2. The seal binds the exact bundle digest and policy digest.
3. The bundle contains the complete three-slot commitments, including the policy's
   human-readable `policy_id`; `attempt_index` selects one exact slot.
4. Terminal cleanup rereads that same pinned seal and compares the selected preview,
   formal scope, ledger path and ledger policy before it can retire anything.

Adding a second free-standing campaign identifier would not authenticate more state
than the seal digest and would introduce a new consistency surface. The live review
spec incorrectly listed “campaign ID” as a distinct terminal invariant. Future briefs
must say “independently pinned campaign seal digest” or explicitly define any new ID
and its security semantics before treating its absence as a defect.

### Terminal seal and window tests — mixed disposition

The claim that no post-start terminal seal-tamper regression exists is false.
`test_changed_seal_in_key_loader_prevents_sdk_and_holds_spending` changes the bundle
after `run_critics` has reserved the ledger, set `_owns_run` and written the controller
start. The resulting failure calls `_terminal`; its assertion verifies that the
allowance remains held and `unused_judge_allowance_retired` is false. The
after-generation variant exercises the same terminal denial later in the run.

The narrower window-coverage claim was valid. `_cleanup_admitted` correctly requires
`seal.sealed_at <= start.started_at < min(policy, observation, authority, envelope
expiry)`, and ordinary admission checks current time before dispatch. Existing tests
already covered campaign deadline capping and evidence that predates sealing. Two new
terminal-path regressions now set the retained start one microsecond before
`sealed_at` and exactly at the earliest committed expiry. Both prove that the exact
allowance remains held, `unused_judge_allowance_retired` is false, and the judge
transport is never called. The confirmed test-evidence gap is closed without changing
runtime code.

## Verification passes

| # | Evidence | Result | Decision |
|---:|---|---|---|
| 1 | Exact campaign verdict and citation normalization | Four upheld findings reduce to three claims; two share omitted contract context | Do not count correlated repetition as independent source proof |
| 2 | Contract, construction and seal-identity trace | Frozen scalar binding, three canonical ownership copies, content-addressed campaign identity | Reject mutable-binding and separate-ID claims |
| 3 | Executable mutation probe | Assignment raised `frozen_instance`; original model stayed unchanged | Confirms the public property does not expose mutable binding authority |
| 4 | Pre-correction campaign-dispatch suite | 21 tests passed in 24.044 seconds, including two post-start changed-seal terminal assertions | Reject the missing terminal seal-tamper claim; isolate the explicit time-boundary gap |
| 5 | Lower/upper terminal-window regressions and affected suite | Starts one microsecond before sealing and exactly at earliest expiry both preserved the held allowance; all 23 tests passed in 24.650 seconds | Close the only confirmed gap without a runtime change |
| 6 | Repository gates | Ruff, formatting, Pyright and diff checks passed; full discovery ran 2,431 tests, with only 31 managed-sandbox loopback-bind errors; all 68 MCP tests then passed with loopback permission and four configured skips | Treat the 31 initial errors as environmental and complete offline verification |

## Finding disposition

| ID | Claim | Severity as asserted | Disposition | Required next action |
|---|---|---|---|---|
| CBR-001 | Exposed `ReviewCampaignBinding` is mutable | high | **Rejected:** inherited frozen configuration and scalar fields make the retained value immutable; constructors also canonical-copy it | Correct reviewer context/spec wording only |
| CBR-002 | Cleanup lacks a distinct campaign ID | high | **Rejected:** the independent seal digest is the content-addressed campaign identity; no separate ID exists in the contract | Replace ambiguous “campaign ID” language with “pinned seal digest” |
| CBR-003 | No post-start seal-change terminal regression exists | blocker | **Rejected:** key-loader and after-generation tests reach terminal cleanup after start and assert non-retirement | Cite the existing tests in future review material |
| CBR-004 | Original terminal-window boundaries lacked focused cleanup tests | blocker | **Accepted and corrected:** direct lower/upper terminal regressions now prove fail-closed behavior | Retain both regressions in the campaign-dispatch gate |

## Exit

- Stop reason: all three claim families were traced through source and executable
  supported paths; the only confirmed gap, CBR-004, now has regression evidence.
- No production runtime defect was demonstrated. The offline test-harness correction
  and repository-wide verification are complete; commit and exact-image rebuild remain.
- No provider call, credential access, spend, ledger mutation or retained campaign
  mutation occurred during this reassessment.
- The prior live verdicts remain immutable and the subject remains unqualified.
