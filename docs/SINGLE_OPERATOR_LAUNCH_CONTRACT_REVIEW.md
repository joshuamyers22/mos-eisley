# Adversarial review: single-operator launch contract

## Review metadata

- Repository: Mos Eisley
- Branch and starting commit: `feat/production-template-guidance` from
  `fa0faafb6f29421e46429001be3932b614f392f0`
- Reviewer: Codex; accountable governance approval by Joshua Myers
- Review date: 2026-09-19
- Product purpose: exact, bounded adversarial code review
- First-party scope: review authorization, observation, campaign acceptance, launch
  admission, focused tests, and their operating documentation
- Requirement and north star: allow Joshua Myers to hold every human launch role
  without representing self-review as independent review
- Rubric: the live-qualification verification record; any role-mode bypass,
  misleading independence assertion, schema-1 regression, credential-order change,
  or spending-authority expansion blocks acceptance
- Context and ceiling: this is not an independent review; three evidence-changing
  implementation/review passes, zero provider spend, stop after focused and full gates

## Executive verdict

- Overall grade: approve
- Release recommendation: approve with the accepted ADR-0005 self-review risk
- Highest risk: one compromised or mistaken operator controls every human assertion
- Strongest property: the weaker trust model is explicit, schema-versioned and cannot
  claim independent observer review
- Recommended first improvement: return to schema-1 separated roles when another
  accountable human is available

## Verification evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Formatting/lint | `make lint` | Passed | 740 files format-checked |
| Static typing | `make check` (`pyright`) | Passed | 0 errors/warnings |
| Focused behavior | selected `unittest` cases | Passed | Shared Joshua signer and mixed-mode rejection |
| Full quality gate | `make check` | Passed | 2,437 tests, 4 skipped, 89% coverage; export, build, and 1,839 wheel tests passed |
| Live/provider | Not run | Intentionally excluded | No credential or spending action authorized by this code change |

## Architecture map

- Domain policy: Pydantic contracts encode schema/operator-mode coherence and signed
  human assertions.
- Application use cases: conformance authorization, observation authentication,
  three-slot acceptance, and launch admission reconstruct exact evidence.
- Infrastructure: Ed25519, ledgers, filesystem records, workers, and provider adapters
  remain outside the operator-mode decision.
- Dependency flow: launch admission consumes campaign/domain contracts; no provider or
  CLI dependency was added to the policy layer.

## Findings

### Accepted high risk: single human can self-authorize misleading evidence

- Location: ADR-0005 and schema-2 launch policy/decision
- Evidence: one identity/key is required across authority, observer, and reviewer roles
- Failure mode: Joshua's mistake, coercion, or compromised host has no human backstop
- Disposition: explicitly accepted by Joshua Myers; schema-2 decision signs self-review
  risk and cannot set the independent-observer assertion
- Reconsideration: higher spend, automation, multi-user use, or an available reviewer

### Resolved high: mixed trust modes could create ambiguous evidence

- Location: campaign bundle, acceptance evaluator, and launch role validation
- Correction: require one operator mode throughout and reject mixed campaign/phase/
  launch policies
- Evidence: `test_single_operator_launch_rejects_mixed_campaign_mode`

### Resolved high: schema 2 could falsely retain the independence claim

- Location: `ReviewLaunchDecision`
- Correction: separated mode requires the independence assertion; single-operator mode
  forbids it and requires `single_operator_self_review_risk_accepted: true`
- Evidence: positive full-path test plus invalid-decision assertion

### Resolved medium: schema-1 hashes could drift from adding a default field

- Location: every operator-mode-bearing contract
- Correction: omit the default `separated` value from serialization and require schema
  2 only for `single_operator`
- Evidence: canonical-byte assertions and the existing schema-1 focused suite

## Clean code and architecture disposition

The shared `ReviewOperatorMode` type prevents spelling drift. Mode validation stays in
domain contracts; cross-artifact role validation is a small pure function at launch
admission. Provider calls, credentials, ledgers, retries, and cleanup were not changed.
The repeated schema/mode condition is intentional at signed artifact boundaries so
each artifact rejects an incoherent version independently.

## Improvement plan

| Priority | Change | Owner | Verification | Status |
|---:|---|---|---|---|
| 1 | Run complete repository gate | Codex | `make check` | Complete |
| 2 | Enroll one real Joshua public key without retaining the private key | Joshua Myers | Reviewed schema-2 policies | Operational input pending |
| 3 | Prefer schema-1 separated mode when another reviewer is available | Joshua Myers | Disjoint signer policies | Future |

## Final challenge answers

The hardest rule is proving meaningful human assessment; software can authenticate a
signature but cannot prove attention or independence. The credible bypasses are mixed
modes, mismatched signer/key pairs, and misleading signed assertions; all now fail
closed. No new retry, deadline, storage, credential, or spending path was introduced.
The complete repository gate passed. The next distinct evidence requires the real
operational inputs listed above; further local self-review without changed evidence
reaches the stopping rule.
