# Brokered evaluation conformance artifacts

`compile_brokered_evaluation` turns a completed host-broker response into a strict,
content-addressed `BrokeredEvaluationArtifact`. Terminal failures can now be compiled
separately from their audit and ledger state instead of disappearing. Both forms are
deliberately separate from `RawResultSet`: synthetic and future credentialed
conformance records cannot enter grading or scoring, and live-result eligibility and
promotion eligibility are literal `false`.

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

Failure compilation requires a terminal `failed` or `cancelled` outcome, an
independently supplied assignment authorization, and the exact named spending ledger.
It carries no response hash, provider request ID, usage, or critique. An absent
pre-reservation ledger entry yields null cost; held, uncertain, and violation entries
retain their recorded exposure. The CLI rejects trust anchors anywhere in the audit
tree or hard-linked to its authorization, and rejects writing derived output into
that audit directory:

```console
mos eval-compile-brokered-failure \
  --expected-authorization trusted/assignment.json \
  --audit-dir private/audit-RUN \
  --spend-ledger private/spend.sqlite \
  --output private/failure-artifact.json
```

Host latency is stored for every schema-3 broker outcome before artifact compilation
and is therefore covered by the audit outcome hash. Actual broker deadlines,
caller cancellation, and generic provider execution errors remain distinct. Schema-1
and schema-2 outcomes remain readable for recovery, but an older failure lacking
trusted latency and classification cannot mint failure evidence.
Latency spans accepted grant dispatch through spending checks, token counting, and
response receipt; it is an end-to-end route observation, not provider compute time.

## Exact-batch inert assembly

`eval-assemble-brokered-results` revalidates one artifact for every request in an
`ExecutionBatch`, rejects omissions and duplicates, verifies assignment route/request
lineage, requires one shared ledger identity, and restores canonical batch order.
Authorization, artifact, outcome, ledger-entry, provider-request, and successful
response identities must be unique.

```console
mos eval-assemble-brokered-results \
  --batch private/calibration-batch.json \
  --artifact private/result-1.json \
  --artifact private/result-2.json \
  --output private/brokered-result-set.json
```

The output is `BrokeredEvaluationResultSet`, not `RawResultSet`. Its schema fixes
credentialed-conformance proof, live raw-result issuance, grading, scoring, retry,
automatic budget release, and promotion to false. This is a completeness checkpoint,
not a relabeling shortcut.

OpenAI documents `max_output_tokens` as covering visible and reasoning token
generation in the [Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create#responses-create-max-output-tokens).
Mos Eisley independently validates the returned response shape and applies its
decoded HTTP byte ceiling before this compilation step.

## Remaining boundary

This path proves provenance and exact-coverage composition with synthetic responses.
It does not prove model availability, provider billing, response conformance, critique
quality, group independence, or network behavior. Credentialed conformance requires
explicit operator authorization and data-transfer consent. Only after those probes
pass may a separately reviewed, authenticated conversion produce live `RawResultSet`
evidence. These artifacts and result sets are never scoreable and must not be relabeled
or copied into recorded-fixture provenance.
