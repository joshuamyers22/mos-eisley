# Agentic Verification Loop: review campaign preparation window

## Objective and authority

- Requirement: extend the pre-dispatch window enough for the manually gated formal three-slot production-qualification trial.
- Operational outcome: all three fixed slots can receive their complete per-slot controller window without lengthening ordinary review-call freshness or weakening live-operation controls.
- Invariants and non-goals: ordinary prepared calls remain capped at 10 minutes; only an explicitly scoped, sealed formal campaign may use 30 minutes; do not change provider, exchange, controller, guardian, phase-authority, spending, retention, retry, or qualification rules.
- Risk class: material authorization-boundary change.
- Implementation owner: Joshua Myers.
- Verifier/accountable approver: Joshua Myers before any subsequent live campaign.
- Revision lineage: `bac7dd24dc5a8a5e20b4b79a229dffc73882c88c` was the original implementation base; `0010970a8960161266841dc59a64c0ef58c48221` is the exact implementation commit and live-campaign revision. The post-campaign correction started from clean descendant `c29e46bee58e8c109a5dc8b49c15f8534cee07fc` and is committed as `6d079cadf2a57da54acf445b6c364ad7aad50bd4`.

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Manual three-slot viability | blocking | Deterministic scope-specific expiry and campaign-dispatch tests | Exact 10-minute standard and 30-minute formal windows; formal dispatch requires the sealed campaign |
| Runtime-boundary preservation | blocking | Provider/controller/watchdog focused suites | All existing 60/120/300/305/360-second assertions pass unchanged |
| Authorization and spending integrity | blocking | Broker admission, campaign, replay, and ledger tests | Exact approval, one-use issue, pricing clipping, no retry, and conservative spend remain |
| Documentation and maintainability | material | Named constant and admission documentation | One source of truth; no configurable unbounded input |

## Budget and stopping rules

- Maximum iterations: the original three evidence-changing passes plus one bounded post-campaign correction pass.
- Elapsed-time or review window: one implementation session.
- Compute/cost ceiling: offline local tests only; no provider calls.
- Pass rule: regression test fails before implementation, focused suites pass after implementation, then every `make check` constituent passes; localhost-dependent tests may run separately with loopback access when the default sandbox forbids socket binding.
- Diminishing-return rule: stop after the full gate and one source/diff audit produce no blocking finding.
- Escalation/domain-input trigger: any need to extend runtime or phase-authority limits, alter spending, add retries, or exceed 30 minutes.
- Rollback or abort condition: any provider/runtime cap changes or unrelated dirty-file overlap.

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Regression boundary | Exact 30-minute and pricing-clipped expectations | W-001 reproduced: old result was ten minutes | Proceed with the bounded freshness-only correction | Focused file: 23 pass, new regression fails |
| 2 | Named bounded constant and documentation | Broker admission, spending envelope, controller, campaign, runner, provider broker and guardian suites | No blocking findings; only pre-dispatch freshness changed | Retain the non-configurable 1,800-second cap and pricing clipping | 107 focused tests passed |
| 3 | Combined repository validation | Full lint/type/source/exported-wheel tests plus constant and diff audit | No product failures; the default sandbox blocked 31 localhost fixture binds, and all affected cases passed with loopback access | Accept the bounded correction; require a fresh commit/image/campaign before live evidence | Ruff and Pyright pass; 2,498 source tests accounted for with 4 skips; 68 affected MCP tests pass with 4 skips; export/build pass; 1,856 wheel tests pass; 88% coverage |
| 4 | Reopened by the formal campaign review | Three live slots completed and qualified operationally; retained verdicts independently identified global freshness scope and ambiguous provenance wording | W-002 high security; W-003 high documentation/provenance | Restore 10 minutes as the default, bind the 30-minute value to explicit `formal_campaign` configuration, fail closed unless the probe has a sealed campaign, propagate scope to judge, and rewrite revision lineage | 107 focused offline broker/launch/probe/campaign tests pass; full repository gate recorded below |
| 5 | Corrected production-image rebuild | Clean exact commit, pinned Dockerfile/base digest, complete offline container gate and separate immutable-image inspection | No finding | Pin the rebuilt Linux/arm64 image; do not treat build verification as campaign or launch evidence | `make container` passes; image `sha256:6672c404f33d595e1a6ce53cebafdf24af5867313882e30fc420a074082c7929`; installed corrected source hashes match the checkout |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| W-001 | `PreparedReviewCall` hardcoded ten-minute expiry | Third fixed slot can inherit too little controller time after manual gates | blocking | Corrected with a bounded 30-minute freshness cap | Deterministic cap/pricing test, focused runtime suites and constant audit pass | Joshua Myers |
| W-002 | `src/mos_eisley/run/review_broker.py`; formal campaign verdicts | The first correction gave every prepared review call the 30-minute freshness window | high | Accepted and corrected: `standard` remains 10 minutes; `formal_campaign` is 30 minutes and cannot execute outside an exact sealed campaign binding | Scope-specific expiry, unbound-formal rejection, campaign-bound positive and mismatch tests | Joshua Myers |
| W-003 | Objective/authority revision wording in this record | The original base commit could be mistaken for the resulting implementation and live-campaign commit | high | Accepted and corrected by naming the base, exact implementation/live revision, and post-campaign correction base separately | Documentation audit against Git ancestry and retained campaign hashes | Joshua Myers |

## Exit

- Stop reason: the bounded post-campaign correction resolved both retained finding classes; no live call was made during correction.
- Rubric result and blocking findings: pass after correction; W-001, W-002 and W-003 are resolved offline.
- Full quality-gate command and result: the correction's default-sandbox `make check` passed Ruff, format and Pyright, then discovered 2,416 source tests: 2,381 passed, 4 skipped and the only 31 errors were denied loopback binds in `test_mcp_http`, `test_mcp_oauth` and `test_mcp_schema`. Those complete modules then passed all 48 tests with loopback access. After the final canonical-compatibility safeguard, all 107 affected review tests, Ruff, format and Pyright passed again. Coverage remains 88%; export verification, sdist/wheel build and all 1,774 installed-wheel smoke tests also pass.
- Production-like replay/fault/rollback evidence: the exact `0010970a` image completed a three-slot campaign with campaign status `accepted`; content verdicts were `reject`, `revise`, `reject` and supplied W-002/W-003. The clean exact correction commit `6d079ca` was rebuilt as immutable Linux/arm64 image `sha256:6672c404f33d595e1a6ce53cebafdf24af5867313882e30fc420a074082c7929`; the complete offline container gate passed, and separate network-disabled inspection confirmed UID/GID `10001:10001`, Python 3.12.14, Mos Eisley 0.1.0, OpenAI SDK 3.11.0, corrected 600/1,800-second constants, matching source hashes, no build tools/tests, and no remaining image-derived container. No provider call was made.
- Remaining uncertainty, owners, and dates: the accepted campaign is evidence for the old exact commit/image, not launch authority for this corrected commit. The corrected image is now verified, but fresh campaign evidence and separately reviewed launch authorization remain required; Joshua Myers.
- Human/domain approval: required before any later live campaign or launch admission.
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: scope-specific freshness and campaign-binding enforcement are covered by regression tests and broker/campaign documentation; the successful campaign and limitations are recorded in `LIVE_REVIEW_FORMAL_QUALIFICATION_2026-09-21.md` and the existing G2 memory fact.
