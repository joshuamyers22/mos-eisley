# G6-02 exact-route resolver: implementation specification

Status: **offline implementation and synthetic tests added; gate review open**,
2026-09-26. This is
G6-02 in the [G6 project plan](G6_ACTIVATED_ROUTING_PROJECT_PLAN.md).
G6-01 is still a [draft operational contract](G6_01_ROUTING_OPERATIONAL_CONTRACT_DRAFT.md),
so this specification grants no implementation sign-off or production authority.
The [resolver](../src/mos_eisley/run/exact_route.py) and
[synthetic tests](../tests/test_exact_route.py) are pure and fixture-testable. It does not contact a provider,
reserve spend, consume an authorization, or authorize dispatch.

## Purpose and existing contracts

For one `ObservablePromptFeatures` value, find the unique frozen profile decision
or the sealed role fallback, then return the **exact** `RouteCandidate` only when
its identity, hard floor, preflight candidate set and current catalog match. A
denial is a normal result, never a request to search for a nearby model or lower
effort. The eventual broker must reverify the complete authority chain and
current controls at use; a resolver result or saved preflight is not a bearer.

Reuse these current types and canonical digests:

| Source | Exact role in G6-02 |
|---|---|
| [`RoutingStudyProtocol.feature_partition` and `RoleRouteConstraint`](../src/mos_eisley/evaluation/routing_protocol.py) | Derive one profile from caller-supplied features and name the permitted/fallback candidate IDs for its role |
| [`FrozenCandidateRoutingPolicy` and `FrozenProfileDecision`](../src/mos_eisley/evaluation/routing_policy.py) | Supply immutable profile action, selected candidate and selected `RouteCandidate` |
| [`SweepPlan.routes` and `RouteCandidate`](../src/mos_eisley/evaluation/models.py) | Supply the unique canonical candidate map and its content-derived `candidate_id` |
| [`RoutingRuntimePreflight`](../src/mos_eisley/run/routing_preflight.py) | Supply non-authorizing policy digest, allowed candidate IDs, unavailable action and expiry |
| [`ModelRegistry` and `ModelSpec`](../src/mos_eisley/core/registry.py) | Check exact catalog identity, effort support and capability facts without using the substituting `resolve` method |

`RouteCandidate` schema 2 pins `backend`, `provider`, `model`, `effort`,
`client_version`, `registry_sha256` and the complete `PromptAsset`. It does **not**
pin the eventual `ModelRequest` tool definitions, output byte/token ceiling,
system/turn payload, provider options or transport endpoint. G6-02 therefore
returns a **selection**, not a runnable request. G6-03 must bind those missing
values to a reviewed, immutable request contract and reject request drift before
credential access. Do not add unqualified output-budget routing under this spec.

## Proposed pure API

Implement in a separate runtime module, for example
`src/mos_eisley/run/exact_route.py`, with no provider, ledger, witness,
filesystem or environment operations:

```python
def resolve_exact_route(
    *,
    plan: SweepPlan,
    sealed_study: SealedRoutingStudy,
    policy: FrozenCandidateRoutingPolicy,
    preflight: RoutingRuntimePreflight,
    features: ObservablePromptFeatures,
    requirements: ExactRouteRequirements,
    registry: ModelRegistry,
    installed_backend: str,
    installed_client_version: str,
    now: datetime,
) -> ExactRouteSelection | ExactRouteDenial: ...
```

`ExactRouteRequirements` is a proposed strict `Contract` with schema version 1:
`role: Identifier`, `output_contract: Identifier`,
`tool_requirements: tuple[Identifier, ...]` (at most 64, sorted and unique), and
`requires_structured_output: bool`. Derive `requirements_sha256` from canonical
contract bytes. The resolver requires role, output contract and tools to equal
the corresponding feature fields. The boolean is an assertion from the caller,
not proof of an approved output-contract mapping; G6-03 must bind this contract
to independently reviewed runtime authority. A production caller may not supply
it ad hoc.

Use frozen, strict contracts for both outputs. A selection contains the
`candidate_id`, complete `RouteCandidate`, `profile_id`, role, source
(`calibrated_route`, `policy_fallback`, or `unseen_profile_fallback`),
`candidate_policy_sha256`, `preflight_sha256`, `requirements_sha256`, catalog
digest and registry verification level. A denial contains a bounded stable
reason code and those safe digests that were validated;
it contains no fallback route to execute. Neither output has an
`activation_authorized`, `dispatch_authorized`, bearer, provider request or
credential field. Errors for malformed objects or violated internal schema may
raise; ordinary ineligibility returns a denial.

The caller must provide an authenticated, current preflight from the complete
source chain before trusting this selection for any later gate. The resolver
can check `preflight.check_current(now)` and digest equality, but it cannot
authenticate the preflight merely by receiving it. Use an explicit UTC `now`;
do not read a clock inside the pure function.

## Deterministic resolution algorithm

1. **Validate provenance.** Require `plan.plan_sha256` to equal both
   `sealed_study.plan_sha256` and `policy.plan_sha256`; require
   `policy.sealed_study_sha256`, `policy.protocol_sha256`,
   `policy.feature_manifest_sha256`, and `policy.dataset_sha256` to match the
   corresponding sealed-study values. Require the preflight policy digest to
   equal `policy.candidate_policy_sha256`, its unavailable action to
   equal `policy.uncalibrated_action`, and its validity window to contain `now`.
   Reject an inconsistent, duplicate or missing plan route map. The full signed
   promotion/activation/control chain is verified by the caller, not re-created
   here.
2. **Classify from the current task.** Locate exactly one role constraint for
   `features.role`. Derive `profile = feature_partition.profile(features)` and
   its content-derived ID. Do not accept a caller-supplied profile ID in place of
   deriving it. The caller is responsible for source-backed feature extraction;
   this function cannot prove that `changed_lines` or a risk tag is truthful.
3. **Select the frozen action.** If the policy contains that profile, require
   the stored `FrozenProfileDecision.profile` to equal the derived profile and
   its role/fallback/considered set to agree with the sealed role constraint.
   `calibrated_route` uses only its selected candidate. `role_fallback` uses only
   the stored sealed fallback. `fail_closed` denies. If the profile is absent,
   use the role's sealed fallback only when both the policy and preflight say
   `role_fallback`; otherwise deny. Never select another calibrated profile,
   rank the eligible set at runtime, or infer a new floor.
4. **Check exact membership.** Require the candidate ID in the role's permitted
   set and in `preflight.eligible_candidate_ids`. Require exactly one matching
   `SweepPlan` route and equality of its complete `RouteCandidate` to the frozen
   selected route when the profile exists. The candidate ID must recompute from
   those route bytes. No alternative ID is tried after a mismatch.
5. **Check the installed catalog.** Require
   `digest(canonical_bytes(registry)) == route.registry_sha256`; installed
   backend and client version must equal the route fields. Find exactly one
   `ModelSpec` with the route provider/model, require `route.effort` in its
   supported efforts, `tool_calling=True` when tools are required, and
   `structured_output=True` when `requirements` demands it. Return the registry
   verification level for later conformance admission; this function does not
   turn `documented` or fixture capability into live conformance. Until an
   authority-bound execution profile exists, G6-02 may test these checks in
   fixtures but may not claim a production runnable route. Do not call
   `ModelRegistry.resolve`; it can return a lower effort with `substituted=True`.
6. **Return a selection or denial.** No fallback is attempted because of catalog,
   capability, preflight or version failure. A later controller may prepare a
   **new** decision for an eligible fallback using fresh authority and before-send
   evidence. The original selection and probability record, if any, remain
   unchanged and cannot be relabeled as the fallback's decision.

The intended stable denial codes are `provenance_mismatch`, `preflight_expired`,
`unknown_role`, `unseen_profile`, `policy_fail_closed`, `policy_inconsistent`,
`candidate_not_eligible`, `route_identity_mismatch`, `registry_mismatch`,
`backend_mismatch`, `client_mismatch`, `model_missing`, `effort_unsupported`,
and `capability_unqualified`. Codes are diagnostic categories, not a precedence
promise when multiple inputs are invalid; tests should assert denial and the
relevant code only for otherwise valid inputs.

## Capability and request binding gap

The current `ObservablePromptFeatures.tool_requirements` and `output_contract`
describe the task profile. `ModelSpec` offers only broad `tool_calling` and
`structured_output` booleans, while `RouteCandidate` has no exact toolset or
output ceiling. A reviewer-approved mapping must decide which
`output_contract` values set `requires_structured_output=True`. Unknown mappings
deny at the caller boundary. The runtime execution profile must pin that
mapping, tool catalog digest, output limits, role minimum and prompt/client
compatibility before G6-03 can
compose a provider request. Changing any of those values starts a new reviewed
measurement/authority lineage; `candidate_id` alone cannot stand in for them.

## Acceptance matrix

Use small, synthetic plans/policies/registries with no provider client or key.
Each case should exercise the pure function. Review its call graph to confirm
it performs no send, ledger or filesystem operation.

| Case | Fixture change | Expected result |
|---|---|---|
| R1 | Exact calibrated profile, approved route, matching registry/backend/client and current synthetic preflight | One exact selection; complete route and digests match inputs |
| R2 | Frozen profile's prescribed `role_fallback` | Only sealed fallback ID is selected |
| R3 | Unseen profile with `role_fallback`, then with `fail_closed` | Sealed role fallback, then denial; no nearest-profile search |
| R4 | Unsupported effort while registry offers a lower one | `effort_unsupported`; no downgraded route |
| R5 | Changed provider, model, backend, client version, prompt bytes or registry digest | Denial; no alternate candidate |
| R6 | Selected/fallback ID absent from permitted set or preflight ID set | Denial even if another candidate is eligible |
| R7 | Policy selected route differs from plan route at the same claimed ID | `route_identity_mismatch` or schema rejection |
| R8 | Expired preflight or wrong policy/unavailable-action digest | Denial before route selection |
| R9 | Missing role, mismatched requirements, unsupported declared capability, missing model or duplicate catalog entry | Denial or strict contract rejection |
| R10 | Selected model disappears from the installed registry, changing its digest | `registry_mismatch`; no in-place fallback to another model or candidate |
| R11 | Mutated feature vector yields a different profile | Only newly derived profile is considered; supplied old profile ID has no input path |

Add a focused regression that proves the existing `ModelRegistry.resolve` would
report `substituted=True` for a synthetic unsupported effort while this resolver
denies the same route. Test both inline and skill `PromptAsset` equality. Use
canonical digest fixtures, not hard-coded substitute IDs. Avoid tests that simply
repeat the implementation branch structure.

## Completion and handoff

G6-02 may be marked complete only after G6-01 is approved, its own owner,
independent reviewer, acceptance protocol and resource ceiling are fixed, and
the focused suite plus repository quality gate pass. The reviewer should inspect
the resolver call graph for side effects and confirm no code path calls
`ModelRegistry.resolve`, constructs a provider request, or treats a preflight as
dispatch authority. The handoff to G6-03 is the exact selection contract plus
its remaining execution-profile/request-binding requirements, not an activated
router.
