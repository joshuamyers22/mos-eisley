# One-assignment OpenAI calibration execution decision

`eval-derive-openai-calibration-execution` and
`eval-authenticate-openai-calibration-execution` create and verify an independent,
short-lived Ed25519 decision for one exact assignment in the 342-item campaign
manifest. Both commands are offline: they reject supported OpenAI credential
variables, make no provider request, create no spending reservation, and require an
explicit offline acknowledgement. `eval-consume-openai-calibration-execution` then
atomically burns that authority into held worst-case spend. It also refuses credentials
and cannot issue a broker grant or send.

The derivation fully reconstructs the campaign manifest from the frozen 360-item
batch, reviewed 18-item seed, and public campaign policy. It then binds:

- one manifest sequence and its original batch position;
- the exact sample, candidate, evaluation request, model, and reasoning effort;
- the deterministic strict-JSON Responses payload used by conformance execution;
- one exact schema-2 spending policy whose rates and token limits equal the
  campaign profile;
- one exact aggregate-ceiling ledger policy, with a ceiling no larger than the
  campaign maximum and enough currently available budget;
- one fresh resolved audit path, also used as the deterministic ledger-entry ID;
- an exact timeout, issue time, expiry, and authority-policy digest.

The decision permits one future exact blinded transfer, credential access,
reservation, and provider request, but it is not itself a send command. The
authenticated receipt still records `credential_accessed=false`,
`spend_reserved=false`, and `provider_request_sent=false`. Explicit local transfer
consent remains required at execution.

Consumption requires separate `--allow-data-transfer` and
`--allow-spend-reservation` acknowledgements. It reserves the profile's complete
schema-2 envelope: every permitted input token at the conservative cache-write rate
and every permitted output token at the output rate. The private preparation contains
hashes and reservation metadata, not the blinded brief or provider payload.

## Ceremony

Create an `openai_calibration_execution_authority_policy` containing the exact
campaign-policy, campaign-manifest, seed, ledger identity, and canonical ledger-policy
digests; a short validity
window; timeout and decision-lifetime ceilings; and one or more sorted, unique
Ed25519 public authorities. Keep private signing keys outside Mos Eisley CLI
arguments and artifacts.

Derive one unsigned decision:

```console
env -u OPENAI_API_KEY -u MOS_OPENAI_KEY \
  mos eval-derive-openai-calibration-execution \
  --batch .mos-eisley/eval/calibration-batch.json \
  --calibration-seed private/openai-live-conformance-gate-v1/calibration-seed.json \
  --campaign-policy policies/openai-calibration-campaign-v1.json \
  --campaign-manifest private/openai-calibration-campaign-v1/manifest.json \
  --spend-policy private/campaign-spend-policy.json \
  --spend-ledger private/campaign-spending.sqlite \
  --execution-authority-policy private/campaign-execution-authorities.json \
  --sequence 1 \
  --audit-dir private/openai-calibration-attempts/0001/audit \
  --request-timeout 60 \
  --issued-at 2026-09-09T14:30:00+00:00 \
  --valid-until 2026-09-09T14:35:00+00:00 \
  --allow-offline-decision \
  --output private/openai-calibration-attempts/0001/decision.json
```

Sign the exact `decision_sha256` with an enrolled Ed25519 authority using a
separate process, then authenticate the signed envelope:

```console
env -u OPENAI_API_KEY -u MOS_OPENAI_KEY \
  mos eval-authenticate-openai-calibration-execution \
  --batch .mos-eisley/eval/calibration-batch.json \
  --calibration-seed private/openai-live-conformance-gate-v1/calibration-seed.json \
  --campaign-policy policies/openai-calibration-campaign-v1.json \
  --campaign-manifest private/openai-calibration-campaign-v1/manifest.json \
  --spend-policy private/campaign-spend-policy.json \
  --spend-ledger private/campaign-spending.sqlite \
  --execution-authority-policy private/campaign-execution-authorities.json \
  --signed-decision private/openai-calibration-attempts/0001/decision-signed.json \
  --audit-dir private/openai-calibration-attempts/0001/audit \
  --allow-offline-authentication \
  --output private/openai-calibration-attempts/0001/execution-authorization.json
```

Consume it into one held reservation. The output parent must already exist, and the
output and audit path must both still be fresh:

```console
env -u OPENAI_API_KEY -u MOS_OPENAI_KEY \
  mos eval-consume-openai-calibration-execution \
  --batch .mos-eisley/eval/calibration-batch.json \
  --calibration-seed private/openai-live-conformance-gate-v1/calibration-seed.json \
  --campaign-policy policies/openai-calibration-campaign-v1.json \
  --campaign-manifest private/openai-calibration-campaign-v1/manifest.json \
  --spend-policy private/campaign-spend-policy.json \
  --spend-ledger private/campaign-spending.sqlite \
  --execution-authority-policy private/campaign-execution-authorities.json \
  --authenticated-execution private/openai-calibration-attempts/0001/execution-authorization.json \
  --audit-dir private/openai-calibration-attempts/0001/audit \
  --allow-data-transfer \
  --allow-spend-reservation \
  --output private/openai-calibration-attempts/0001/prepared.json
```

## One-use boundary and remaining work

The audit-path digest is the ledger-entry ID. Authentication verifies that the ID is
absent; consumption relies on the ledger's immediate transaction to create the exact
held entry or reject a concurrent duplicate. Held spend is never automatically
released. If the process fails after reservation but before writing the preparation,
the ledger remains conservatively held and `spend-ledger-status` provides recovery
inventory; the signed authority must not be retried.

The nested authentication's `ledger_entry_absent_verified=true` is explicitly
historical: it describes the earlier authentication timestamp. The outer preparation
is the later current state and records that authority as consumed with spend held.

The prepared receipt is not a bearer token or send authority. The next provider
boundary must fully reverify it, require the exact held entry, check the installed
SDK/client contract and remaining timeout, and obtain a fresh same-invocation transfer
acknowledgement before credential access. It grants no retry, automatic budget
release, grading, scoring, promotion, routing activation, provider-authorship claim,
billing reconciliation, or account-wide spending guarantee.
