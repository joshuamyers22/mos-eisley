# OpenAI credentialed-conformance request contract

Mos Eisley now has a deterministic request builder for one blinded OpenAI
evaluation assignment. This is preparation for a future credentialed command; it
does not expose a live entry point and its tests make only synthetic HTTP requests.

`build_openai_conformance_payload` requires one exact sample in an
`ExecutionBatch`, an `openai` route, and a reviewed spending policy for the same
model. The model and reasoning effort come from the assignment. The output-token
ceiling comes from the policy. The user content is only canonical `Brief` JSON;
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

## Still disabled

There is no `openai-conformance` CLI command yet. Before adding one, lifecycle
management must create and close the official SDK client on the same async loop as
the broker callback, persist the trusted authorization separately before dispatch,
require explicit data-transfer consent, and save the resulting non-scoreable
artifact exclusively. Tests must prove every missing/mismatched input fails before
reading `OPENAI_API_KEY` or starting Docker. Running the command will then require
separate operator authorization because it sends brief content and may incur cost.
