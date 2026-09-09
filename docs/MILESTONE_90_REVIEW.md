# Milestone 90 adversarial review: calibration authority consumption

## Disposition

Accept as a precredential, no-send consumption boundary. It converts one current,
authenticated calibration decision into one exact held worst-case reservation. Do
not treat the preparation as a provider grant, proof of transfer, or completed run.

## Findings and controls

- **Check-then-insert can race.** Source inspection is advisory; the SQLite
  `BEGIN IMMEDIATE` reservation is the consumption point. A competing insertion with
  the same deterministic audit-path ID makes the loser fail as already consumed.
- **A narrow reservation could understate exposure.** Consumption reserves the full
  profile input ceiling at the schema-2 cache-write rate plus the full output ceiling,
  and requires that total to equal the independently signed maximum cost.
- **Consent could be inferred from a prior ceremony.** The command requires distinct
  local transfer and spend-reservation acknowledgements. It does not accept consent
  merely because the decision was signed or authenticated.
- **Credential presence could collapse preparation into accidental dispatch.** The
  command rejects both supported credential variables before reading source artifacts.
  Its implementation contains no provider client, broker grant, or transport call.
- **Output collision could consume spend before a predictable write failure.** A
  fresh existing-parent output is required and all input, ledger, audit, and output
  paths must be disjoint before reservation. Unavoidable post-reservation failures
  retain the held entry and authorize no retry or release.
- **A substituted ledger could inherit the decision.** The canonical ledger policy,
  ledger identity, campaign aggregate ceiling, deterministic entry ID, spend policy,
  request hash, and reservation hash are all reverified before the atomic insert.
- **A stale preparation could reach a credential boundary.** Consumption requires
  enough decision lifetime for the entire request timeout. Offline verification
  repeats source, signature, policy, held-state, freshness, and timeout checks.
- **The preparation could leak the blinded sample.** It retains hashes and spending
  metadata but not the provider payload or brief.

## Residual risks

The local preparation is not independently signed; its authority comes from the
nested signed decision and exact held ledger state. A crash after ledger commit but
before output persistence leaves a held entry without a preparation, deliberately
favoring bounded exposure over retry. Filesystem trust, clock integrity, authority
revocation, provider availability, SDK equality, provider authorship, actual usage,
quality, and billing finality remain outside this boundary. The future credentialed
consumer must re-obtain same-invocation consent and cannot release or reuse this held
reservation automatically.
