# OpenAI credentialed-conformance request contract

Mos Eisley has a deterministic request builder and fail-closed CLI lifecycle for
one blinded OpenAI evaluation assignment. The command is paid-capable, but its
tests replace both provider dispatch and Docker execution; this repository has not
yet recorded a credentialed conformance result.

`build_openai_conformance_payload` requires one exact sample in an
`ExecutionBatch`, an `openai` route, and a reviewed spending policy for the same
model. The model, reasoning effort, and exact instructions come from the assignment.
The output-token ceiling comes from the policy. The user content is only canonical
`Brief` JSON;
private labels, case IDs, split, mapping, expected findings, credentials, endpoints,
and spending authority are not included. Tools are empty, parallel tool calls are
disabled, storage is false, and input truncation is disabled.

The response uses strict JSON Schema derived from the immutable `Critique` contract.
Schema normalization removes presentation/default keywords and makes every object
property required with `additionalProperties: false`; nullable fields remain
nullable. OpenAI's [Responses API reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create#responses-create-text)
documents `text.format` for structured JSON output. Fixture tests verify the exact
schema through the installed official SDK and bounded HTTP client.

The spending controller permits this host-created `text` configuration while
retaining its existing one-use request snapshot, token count, reservation, shared
ledger, model/tier/usage checks, and conservative failure handling. A worker still
cannot choose or modify the schema because its capability is bound to the exact
serialized provider request.

## Explicit command

`openai-conformance` requires the blinded batch/sample, reviewed expiring spending
policy, existing shared ledger, absolute Docker executable, immutable image ID,
fresh audit directory, and two fresh output files. It derives model and effort from
the assignment; there are no command-line overrides. Consent is checked before any
input read, and all other preflight checks finish before `OPENAI_API_KEY` is read or
Docker starts. The trusted audit parent must already exist, and the three output
paths may not contain or overlap one another.

```console
mos openai-conformance \
  --batch blinded-batch.json --sample-id <sha256> \
  --spend-policy spend-policy.json --spend-ledger spending.sqlite \
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
artifact or permits retry.

Running this command requires separate operator authorization because token
counting and generation send the blinded brief to OpenAI and generation may incur
cost. No live call was made while implementing or testing this lifecycle.

The later [skill runtime conformance attestation](SKILL_RUNTIME_CONFORMANCE.md) binds
an enrolled observer's signed claim to the exact settled and content-verified skill
runtime publication. It remains a claim-authentication layer, not provider or billing
proof, and likewise makes no quality or promotion claim.
