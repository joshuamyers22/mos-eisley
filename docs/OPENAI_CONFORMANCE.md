# OpenAI credentialed-conformance request contract

Mos Eisley has a deterministic request builder and fail-closed CLI lifecycle for
one blinded OpenAI evaluation assignment. Its automated tests replace both provider
dispatch and Docker execution. After merge of the exact-request hardening, one
operator-authorized live probe completed and its private evidence authenticated; the
repository commits only the bounded disposition, not the private artifacts.

`build_openai_conformance_payload` requires one exact sample in an
`ExecutionBatch`, an `openai` route, and a reviewed spending policy for the same
model. The model, reasoning effort, and exact instructions come from the assignment.
The output-token ceiling comes from the policy. The user content is only canonical
`Brief` JSON;
private labels, case IDs, split, mapping, expected findings, credentials, endpoints,
and spending authority are not included. Tools are empty, parallel tool calls are
disabled, storage is false, input truncation is disabled, the service tier is
`default`, and both streaming and background execution are explicitly false. These
generation controls therefore participate in the request hash reviewed by the
ceremony instead of being inferred from API or SDK defaults.

The response uses strict JSON Schema derived from the immutable `Critique` contract.
Schema normalization removes presentation/default keywords and makes every object
property required with `additionalProperties: false`; nullable fields remain
nullable. OpenAI's [Responses API reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create#responses-create-text)
documents `text.format` for structured JSON output. Fixture tests verify the exact
schema through the installed official SDK and bounded HTTP client.

The spending controller permits this host-created `text` configuration while
retaining its existing one-use request snapshot, token count, reservation, shared
ledger, model/tier/usage checks, and conservative failure handling. It rejects
conflicting storage, truncation, service-tier, streaming, or background values rather
than silently rewriting them. The conformance builder's request is unchanged at the
controller-to-transport generation boundary. Generation-only controls are removed
from the separate input-token-count request. A worker still cannot choose or modify
the schema because its capability is bound to the exact serialized provider request.

## Explicit command

`openai-conformance` requires the blinded batch/sample, reviewed expiring spending
policy, existing shared ledger, separately prepared conformance policy, independent
authority policy and signed short-lived execution authorization, absolute Docker
executable, immutable image ID, fresh audit directory, and two fresh output files. It
derives model and effort from the assignment; there are no command-line overrides.
Local consent is checked before any input read. The
[no-send ceremony](CONFORMANCE_CEREMONY.md) and live preflight bind and recheck the
exact request, spending identities, audit-derived unused ledger entry, policy window,
and installed SDK version. The separate
[signed authorization](EVALUATION_CONFORMANCE_AUTHORIZATION.md) authenticates exact
blinded-transfer and spend authority before `OPENAI_API_KEY` is read or Docker starts. The
trusted audit parent must already exist, and the policy and three output paths may
not contain or overlap one another.

```console
mos openai-conformance \
  --batch blinded-batch.json --sample-id <sha256> \
  --spend-policy spend-policy.json --spend-ledger spending.sqlite \
  --conformance-policy trusted/conformance-policy.json \
  --conformance-authority-policy trusted/conformance-authority-policy.json \
  --signed-conformance-authorization trusted/signed-authorization.json \
  --docker /usr/local/bin/docker --image sha256:<64-hex-image-id> \
  --audit-dir private/audit \
  --authorization-output trusted/authorization.json \
  --artifact-output private/conformance.json \
  --allow-data-transfer
```

The trusted authorization and final artifact must be outside the audit directory
and are created exclusively. The authorization is persisted before dispatch. The
SDK client and bounded HTTP client are created and closed on the broker callback's
event loop, while the credential and endpoint remain host-only. A completed reply
must agree with the audit chain and settled ledger before the strict, explicitly
non-scoreable artifact is written. After dispatch, failure leaves the authorization,
audit, and conservative ledger receipt for recovery inspection and never writes an
artifact or permits retry. Schema-4 audit diagnostics retain only a fixed local stage
and coarse SDK exception category. They discard exception text and bodies and do not
prove provider receipt, billing, or the exact remote cause.

Running this command requires separate operator authorization because token
counting and generation send the blinded brief to OpenAI and generation may incur
cost. Automated tests do not make live calls.

The independent authorization signs the deterministic request hash rather than a
second cleartext copy of the request. The authorizer therefore needs the blinded
batch, reviewed policies, and trusted deterministic builder (or an independently
rendered request) to understand the bytes represented by that hash. A future schema
may embed a human-reviewable request projection without weakening hash verification.

After a real successful probe, the separate
[evaluation conformance receipt](EVALUATION_CONFORMANCE.md) can authenticate an
enrolled observer's claim against the exact assignment, independently retained
authorization, audit chain, and settled ledger. That receipt remains one-assignment,
non-scoreable evidence and does not prove provider authorship or billing.

The first such receipt was authenticated on 2026-09-07 for one blinded
`gpt-5.6-luna` assignment at reasoning effort `low`. See the
[live-evidence adversarial review](MILESTONE_52_REVIEW.md) for the verified counts,
hashes, and deliberately unproven claims. It does not authorize conversion or
empirical routing.

The later [skill runtime conformance attestation](SKILL_RUNTIME_CONFORMANCE.md) binds
an enrolled observer's signed claim to the exact settled and content-verified skill
runtime publication. It remains a claim-authentication layer, not provider or billing
proof, and likewise makes no quality or promotion claim.
