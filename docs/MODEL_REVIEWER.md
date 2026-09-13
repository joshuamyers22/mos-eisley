# Canonical model review bridge

`providers.model_reviewer.ModelReviewer` implements the existing `Reviewer`
interface through an explicitly supplied `ModelClient`. This library boundary is
tested with local clients. It does not create a transport, load credentials, or
enable a live CLI/terminal mode. The terminal `/review` remains recorded.

Each critic receives one fresh user turn containing only its brief and persona.
The judge receives the brief and deduplicated findings from the existing review
pipeline, paired with their canonical SHA-256 IDs. Supplying IDs avoids asking a
model to calculate hashes. Critic IDs, provider identities and personas are absent
from the judge projection; arbitrary text already present in a brief/finding is
preserved. There is no chat transcript, memory lookup, tool roster or tool dispatch.
Frozen guidance already incorporated into `Brief.constraints` remains review data.

Provider/model pairs resolve through the explicit model registry, including its
effort fallback. The judge model is selected separately at construction. A system
prompt describes the role and embeds the expected JSON schema. This is prompted
JSON with local validation, not provider-native structured output. Long input JSON
is split into ordered text blocks; their concatenation exactly reconstructs it.
Prompt instructions are advisory isolation aids, not a sandbox against malicious
review content. Deterministic validation remains mandatory.

Admission counts the complete canonical model request, including prompt/schema,
block wrappers and output settings, against the resolved input byte budget. The
response cap includes the entire canonical response, including opaque reasoning,
usage and request IDs. Reported byte/token usage is also checked against configured
limits. These local acceptance checks do not bound transport allocation or grant
spending authority: the existing bounded transport and spending controller must
enforce those limits before a future live integration dispatches.

Only a completed assistant response containing text and optional reasoning can
produce a result. Text blocks concatenate; reasoning is excluded from the answer.
The answer must be exactly one JSON object with every top-level contract field,
an integer schema version of 1, no extra fields and no duplicate keys at any depth.
Typed contract validation enforces nested fields. Refusal/filtering, truncation,
tools, malformed JSON, omitted answers and budget violations become coarse provider
errors. There is one client call per role, no repair/retry loop, and cancellation
propagates to the client. A caller-provided client must also disable transport
retries to preserve the eventual one-exchange spending contract.

The review pipeline still validates exact quoted evidence, critic/provider quorum,
finding deduplication and judge IDs, then computes the verdict deterministically.
Invalid evidence or an insufficient critic quorum prevents judge dispatch; unknown
or duplicate upheld IDs cannot produce acceptance. Model output alone cannot
authorize execution, writes, routing or spending.

G2's next integration must provide an admitted broker client for each exact
provider request, pin transfer and pricing selections, reserve aggregate critic
and judge spend, retain evidence, and validate cancellation with credentialed
conformance. Guidance admission is separate and still required at runtime.
Model labels or passing local fixtures do not establish provider independence or
live quality. See [the delivery roadmap](ROADMAP.md) and
[the project plan](mos-eisley-plan.md#26-integrated-project-review-and-delivery-contract).

Rollback removes this library adapter and its tests/docs. Existing recorded
packet schemas, run artifacts, terminal commands and provider commands are unchanged.
