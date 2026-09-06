# Brokered evaluation conformance artifacts

`compile_brokered_evaluation` turns a completed host-broker response into a strict,
content-addressed `BrokeredEvaluationArtifact`. It is deliberately separate from
`RawResultSet`: these synthetic and future credentialed conformance records cannot
enter grading or scoring, and `promotion_eligible` is the literal value `false`.

Compilation requires all of the following to agree:

- the independently trusted assignment authorization and hash-linked broker audit;
- a finished `response_received` outcome whose hash matches the exact `BrokerReply`;
- the exact shared ledger identity and a settled entry for that authorization;
- a valid OpenAI Responses payload with a provider request ID, completed text turn,
  token usage, no tool call, and no incomplete/filtered/error stop;
- text that is exactly valid strict `Critique` JSON.

The resulting artifact embeds the assignment authorization and its hash, audit
outcome hash, provider-response hash, provider request ID, token usage, settled
micro-USD charge, host-recorded latency, and parsed critique. Its own canonical hash
binds those fields. No raw API key, bearer grant, or provider exception is included.

Host latency is stored in schema-2 broker outcomes before artifact compilation and
is therefore covered by the audit outcome hash. Schema-1 outcomes remain readable
for recovery, but lack trusted latency and cannot mint a conformance artifact.
Latency spans accepted grant dispatch through spending checks, token counting, and
response receipt; it is an end-to-end route observation, not provider compute time.

OpenAI documents `max_output_tokens` as covering visible and reasoning token
generation in the [Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create#responses-create-max-output-tokens).
Mos Eisley independently validates the returned response shape and applies its
decoded HTTP byte ceiling before this compilation step.

## Remaining boundary

This milestone proves provenance composition with synthetic responses. It does not
prove model availability, provider billing, response conformance, critique quality,
group independence, or network behavior. Credentialed conformance requires explicit
operator authorization and data-transfer consent. Only after those probes pass may
a separately reviewed conversion produce live `RawResultSet` evidence. That later
conversion must preserve failures and exact coverage; this artifact itself is never
scoreable and must not be relabeled or copied into recorded-fixture provenance.
