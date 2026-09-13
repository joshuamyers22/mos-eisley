# Explicit review launch configuration

`review-launch-preview` assembles the existing guidance, canonical request,
spending-envelope and controller contracts from explicit host-selected inputs.
It prints exact requests and aggregate exposure without loading credentials,
constructing a provider client, starting Docker, creating a run directory or
reserving spending.

```sh
mos-eisley review-launch-preview \
  --config /private/reviews/configuration.json \
  --workspace /work/project \
  --guidance-storage /private/guidance \
  --prepared /private/reviews/prepared.json \
  --expected-prepared-sha256 "$PREPARED_REVIEW_SHA256" \
  --guidance-policy /private/policies/project.json \
  --expected-guidance-policy-sha256 "$GUIDANCE_POLICY_SHA256" \
  --spend-ledger /private/spending.sqlite \
  --review-dir /private/reviews/new-run \
  --json
```

The configuration is a bounded `ReviewLaunchConfiguration` JSON object containing
an explicit registry snapshot, one to eight `LaunchCritic` entries (each with a
`CriticSpec` and schema-2 `SpendPolicy`), judge model/spending selection, reasoning
effort, byte/token `BudgetPolicy`, `ReviewPolicy`, whole-review time limit and
aggregate micro-USD ceiling. Its mode is `brokered_review_launch_configuration`.
The registry is configuration data; a `live_conformance` label is not proof.

For example, an owner can serialize the configuration from already selected inputs:

```python
from pathlib import Path
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.review_launch import LaunchCritic, ReviewLaunchConfiguration

configuration = ReviewLaunchConfiguration(
    registry=selected_registry,
    critics=tuple(
        LaunchCritic(critic=critic, spending=policy)
        for critic, policy in selected_critic_policies
    ),
    judge_model=selected_judge_model,
    judge_spending=selected_judge_spending,
    effort=selected_effort,
    budget=selected_budget,
    policy=selected_review_policy,
    total_seconds=120,
    max_total_microusd=selected_aggregate_ceiling,
)
Path("configuration.json").write_bytes(canonical_bytes(configuration))
```

Prepared guidance and its expected hash are mandatory. The caller explicitly
selects the current workspace, guidance store and owner policy; saved policy paths
do not select them. Current guidance is checked before and after projection. The
preview includes the frozen guided brief, while unselected private policy prose
stays out of the model requests. See [guidance admission](REVIEW_GUIDANCE_ADMISSION.md).

The command rejects duplicate JSON keys, oversized configuration, mismatched model
spending policies, unsupported providers, reasoning-effort substitution, invalid
judge output budgets, expired pricing, unavailable ledger capacity and existing
output paths. It never creates a missing ledger. The existing default two-provider
quorum remains unchanged. OpenAI-only configurations require an explicitly selected
one-provider policy; that selection is not made automatically.

Success prints one `review.launch.preview` object, with canonical configuration,
registry and guidance hashes plus the complete `ControllerCriticPreview`. Exit
status zero means the configuration preview was built. It does not mean live
launch is available. The output always declares:

- `conformance_status: "review_controller_conformance_required"`
- `live_launch_available: false`
- `credential_access_authorized: false`
- `provider_dispatch_authorized: false`
- `reservation_created: false`

Existing signed evaluation-probe receipts cover a different request/lifecycle
path. This configuration schema does not accept those receipts, conformance
claims or arbitrary execution fields as a substitute for credentialed review
conformance. A credentialed review-path harness and a launch admission decision
remain required before enabling a live command. No provider call is authorized
by this preview, by a registry label, or by successful fixture tests.

[Signed phase authorization](REVIEW_CONFORMANCE_AUTHORIZATION.md) now provides
independent critic/judge signature checks alongside local approval. Credentialed
execution and authenticated observations remain outstanding; signatures alone do
not change this preview's conformance or activation status.

Each invocation creates fresh *in-memory* attempt identities. Consequently, the
controller preview hash changes even when the configuration hash stays the same;
there is no saved executable handle to resume or approve in another process.
This command diagnoses configuration and transfer content. The existing
[approval flow](REVIEW_APPROVAL_FLOW.md) still requires a fresh, admitted controller
and separate user decisions at both transfer boundaries.

Acceptance uses synthetic models and a zero-dollar provider budget. Tests cover
current guidance, policy/model/budget mismatches, quorum, unchanged ledger bytes,
missing ledgers, output-path preservation, duplicate keys, registry-label and
conformance-receipt substitution, CLI credential isolation and repeated previews.
The source and installed-wheel suites share the same tests.
