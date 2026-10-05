# G6-02 exact-route resolver technical review

Status: **technical review completed; independent G6-02 gate open**,
2026-09-27. This is a source and synthetic-evidence review of the
[G6-02 specification](G6_02_EXACT_ROUTE_RESOLVER_SPEC.md). It is not an
independent reviewer signature, G6-01 approval, G5 qualification, a current
provider observation or dispatch authority. The [G6-01 technical
review](G6_01_TECHNICAL_GATE_REVIEW.md) left that prerequisite gate open.

## Reviewed snapshot and method

Repository HEAD during review was
`805a5161a003c40e3c0c15adb32e62d939f1ea66`. The G6-02 specification,
[resolver](../src/mos_eisley/run/exact_route.py) and
[focused tests](../tests/test_exact_route.py) had no uncommitted changes and
matched the SHA-256 values in the [G6-01 through G6-04 review
packet](G6_01_TO_G6_04_INDEPENDENT_REVIEW_PACKET.md):

| File | SHA-256 |
|---|---|
| G6-02 specification | `e9824de5e8bd32a0aa2beeb5acd7ffbf743ae7ac2b7f8b1eafed66670cfe9e8d` |
| `exact_route.py` | `e4bd2dbf72e4cbc9eea6eeda246920e7ec7c93a4af9ed85941d0a327d043c969` |
| `test_exact_route.py` | `bbf9b667f3d4889774955b3145d3e79de13a8308c6318e7c3f51570ee176541e` |

I traced the resolver and its called contract validators in
[`ModelRegistry`](../src/mos_eisley/core/registry.py),
[`SweepPlan`/`RouteCandidate`](../src/mos_eisley/evaluation/models.py),
the [frozen policy](../src/mos_eisley/evaluation/routing_policy.py),
[feature partition](../src/mos_eisley/evaluation/routing_protocol.py) and
[preflight](../src/mos_eisley/run/routing_preflight.py). I also inspected the
[G6-03 inert transaction](../src/mos_eisley/run/routing_transaction.py)
handoff. This review used synthetic fixtures only and did not read protected
sampling or outcome stores.

The focused command
`uv run --frozen python -m unittest tests.test_exact_route` passed **10 tests**.
The adjacent `tests.test_protocol_budget` suite passed **10 tests**, including
duplicate-model schema rejection and the registry's substituting `resolve`
behavior. Ruff and Pyright checks of the resolver and focused tests passed.
Ad hoc synthetic reviewer probes returned `provenance_mismatch` for a changed
preflight unavailable action, `route_identity_mismatch` for changed frozen
provider/model, `unknown_role` for an unregistered role, and
`candidate_not_eligible` for a fallback omitted from preflight. These probes
are reproducible observations, not retained acceptance tests.

## Source assessment

The resolver is a pure function over supplied contracts and explicit UTC time.
Its call graph has no provider, ledger, witness, filesystem or environment
operation and does not call `ModelRegistry.resolve`. It derives the profile
from the supplied feature vector, uses the one frozen action or sealed role
fallback, checks candidate membership in the role and preflight sets, matches
the full content-derived route against the plan and policy, then checks the
installed registry digest, backend, client version, exact model, effort and
broad capability flags. A registry change or failed capability check produces
a denial; it does not search for a nearby route or lower effort. The selection
contains no provider request or dispatch field.

This is an **offline selection claim only**. The resolver cannot authenticate
the source of the preflight, the truth of task features, the installed client
identity, current external catalog/conformance/pricing observations or the
caller's `requires_structured_output` assertion. It returns the registry's
verification level, including `fixture` or `documented`, without promoting it
to live conformance. The credential-owning broker must independently verify
all those facts before any send.

## R1–R11 acceptance trace

| Case | Evidence observed | Remaining issue |
|---|---|---|
| R1 exact selected route | `test_exact_calibrated_route_is_inert` checks full route equality, source, digests and no dispatch/request field. | Independent reviewer must compare the source chain, not just the synthetic constructor. |
| R2 frozen fallback | `test_frozen_and_unseen_fallback_are_exact` checks the sealed fallback route. | None in the pure selection logic. |
| R3 unseen profile/fail closed | `test_unseen_profile_and_explicit_fail_closed_deny` checks both; the prior test covers unseen fallback. | None in the pure selection logic. |
| R4 unsupported effort | `test_unsupported_effort_never_uses_registry_downgrade` first proves registry substitution, then checks resolver denial. | Actual provider effort support still needs G6-05 conformance evidence. |
| R5 route/client/prompt drift | Existing tests cover backend/client drift, changed catalog and inline/skill prompt changes. Reviewer probes covered frozen provider/model drift. | Provider/model probes and same-mode skill-content drift are not retained in the focused suite. |
| R6 candidate membership | `test_provenance_expiry_and_eligibility_fail` denies a selected candidate outside preflight; reviewer probe denied a fallback omitted from preflight. | The fallback-specific probe is not a retained focused test. |
| R7 frozen route differs from plan | `test_route_and_prompt_substitution_fail` produces `route_identity_mismatch` for altered frozen route bytes. | This uses `model_copy` to create an internally inconsistent fixture, which is appropriate for a negative boundary test. |
| R8 preflight/provenance | Focused test covers expiry and policy-plan mismatch; reviewer probe covers changed unavailable action. | The changed-action probe is not a retained focused test. |
| R9 role/requirements/catalog | Focused tests cover requirements mismatch, broad capability denial and missing model. Reviewer probe covers unknown role; `ModelRegistry` rejects duplicate provider/model pairs in `test_protocol_budget`. | Unknown-role probe is not a retained focused test. |
| R10 installed registry loses model | Focused tests separately show registry-digest mismatch and `model_missing` when the frozen route is rebuilt against a registry without its model. | No in-place fallback is observed. |
| R11 changed feature vector | The unseen-profile tests mutate a risk tag and resolve from the derived profile. The API accepts no supplied profile ID. | Numeric-feature mutation is not separately retained, though the same partition function is used. |

The focused suite covers every major decision branch, but several specific
R1–R11 matrix variations were checked only in transient reviewer probes.
Before a formal G6-02 acceptance, freeze those probes as tests or record an
independent rationale that the existing source and tests suffice.

## Findings and gate decision

| ID | Class | Finding and closure |
|---|---|---|
| G602-01 | Gate blocker | G6-01 is not approved. G6-02's exit explicitly depends on that approval. Obtain the real G6-01 owner, operations and independent security decision first. |
| G602-02 | Gate blocker | G6-02 has no recorded implementing owner, independent reviewer, frozen acceptance protocol or resource ceiling. Record distinct roles, exact source/test hashes, negative oracles and verification budget before formal acceptance. |
| G602-03 | Contract discrepancy | The specification says denials contain validated safe digests; `ExactRouteDenial` contains only `reason`. The current behavior is safe and bounded, but the reviewer must either amend the specification to say reason-only or add the required digest fields and tests before signing the exact contract. |
| G602-04 | Coverage item | Provider/model drift, fallback preflight omission, changed unavailable action, unknown role and numeric-feature drift lack dedicated retained tests in the G6-02 suite. The first four were observed in ad hoc probes; preserve the final accepted evidence or document why the existing matrix covers them. |
| G602-05 | Handoff constraint | `requires_structured_output` is a caller assertion. In a synthetic probe, setting it to `False` still returned a selection for the same output contract. This matches the G6-02 specification; G6-03 must bind the output-contract mapping, exact toolset, limits and provider options to reviewed authority. No caller may treat this selection as a runnable request. |

**Technical conclusion:** no source path was found that substitutes a lower
effort or another candidate after an exact-route failure. The pure resolver is
suitable as offline engineering evidence. **The independent G6-02 milestone
remains open** until G602-01 through G602-04 receive recorded dispositions and
an independent reviewer accepts the exact snapshot. G602-05 is a required
later broker handoff and blocks live use, not pure fixture execution.

| Independent decision field | Current value |
|---|---|
| G6-01 approval reference | Open |
| Implementing owner and independent G6-02 reviewer; separation basis | Open |
| Frozen R1–R11 protocol, source/test digests and resource ceiling | Open |
| G602-03/G602-04 disposition and reviewed negative evidence | Open |
| Dated accept/reject decision for this exact resolver snapshot | Open |

The existing preflight's literal dispatch denial remains unchanged. Sampling
receipts are metadata only; this review did not infer missing sampling
probabilities, independence groups, labels or splits.
