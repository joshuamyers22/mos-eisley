# Routing activation eligibility

Mos Eisley can derive a short-lived, non-executing eligibility receipt from an
authenticated routing promotion and fresh operational attestations. The receipt is
an input to a future deployment controller. It does not install a policy, mutate
configuration, call a provider, or route traffic.

Issuance requires three domain-separated Ed25519 signatures from distinct trusted
keys:

1. an activation-policy signature over the exact routes, normalized cost ceilings,
   freshness limit, receipt lifetime, minimum control sequence, and validity window;
2. an operational-readiness signature over exact route identities and the asserted
   catalog, price, conformance, and drift evidence; and
3. a control signature over a fresh emergency-stop and revocation state.

Every activation authority identity and public key must also be absent from the
calibration and holdout grader/resolver policies and from the promotion-authority
policy. The three activation signers must differ from one another. The activation
authority policy is an independently distributed trust root.

The operational snapshot binds the authenticated promotion receipt, frozen candidate
policy, and signed activation policy. It must cover exactly every selected route and,
when the frozen policy uses `role_fallback`, every fallback route. Route equality
includes provider, backend, model, effort, and capabilities. Missing, extra, or
substituted routes fail closed; `allow_model_substitution` is always false.

The verifier reconstructs the complete calibration, holdout, and promotion chain,
then verifies all three activation signatures and gates. Issuance succeeds only when:

- promotion readiness is authenticated and true;
- the policy, operational observations, and control state are current under an
  explicit UTC clock;
- catalog availability, conformance, and drift are all asserted as passing;
- normalized route cost does not exceed the signed route-specific ceiling;
- the control sequence meets the signed minimum, emergency stop is clear, and the
  candidate policy and promotion receipt are not revoked; and
- all exact required routes are present under the signed pricing basis.

The receipt expires at the earliest of the signed policy, control state, route
evidence, or configured maximum lifetime. Consumers must call
`verify_routing_activation_eligibility` with the complete source set and current time;
the standalone JSON is not self-authenticating.

```console
mos eval-issue-routing-activation-eligibility \
  --signed-activation-policy trusted/signed-activation-policy.json \
  --signed-operational-snapshot private/signed-operational-snapshot.json \
  --signed-control-state trusted/signed-control-state.json \
  --activation-authority-policy trusted/activation-authorities.json \
  --promotion-receipt private/routing-promotion-receipt.json \
  --output private/routing-activation-eligibility.json \
  ...complete calibration, holdout, and promotion inputs...
```

Private keys are never accepted by the CLI. Library signing helpers exist for
external custody integrations and tests. Production signers should independently
construct and review their payloads before signing.

## Deliberate limits

The route evidence fields are signed operator attestations with content digests.
Mos Eisley does not fetch provider catalogs or prices and does not inspect the
referenced conformance or drift evidence. A signature proves which assertion an
enrolled key made; it does not prove that the assertion or referenced evidence is
correct.

`normalized_cost_microusd` and `pricing_basis` are operator-defined comparison units,
not a universal provider invoice calculation. Their method, source, effective date,
cache treatment, and token assumptions require external review.

A signed control state proves its sequence and validity window, not that it is the
latest state ever issued. An older still-valid state can be replayed until it expires
unless the consumer maintains an external monotonic sequence anchor. The signed
minimum sequence, evidence-age bound, and short expiry limit this window but do not
replace a live revocation service.

System-clock integrity, evidence collection, trust-policy distribution, private-key
custody, key revocation, signer organizational independence, and monotonic control
delivery remain outside this milestone. The receipt contains literal
`runtime_activation_authorized: false` and
`configuration_mutation_authorized: false`; no runtime component consumes it.
