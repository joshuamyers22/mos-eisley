# Canonical model review bridge

`providers.model_reviewer.ModelReviewer` implements the existing `Reviewer`
interface through an explicitly supplied `ModelClient`. This library boundary is
tested with local clients. It does not create a transport, load credentials, or
enable a live CLI/terminal mode. The terminal `/review` remains recorded.

Each critic receives one fresh user turn containing only its brief, persona, and—
for critic-request schema 2—a compact catalog of deterministic diff citation-unit
descriptors. The catalog does not duplicate diff text. It identifies the whole raw
patch plus the exact before/after view of each hunk; SHA-256-bearing IDs bind each
descriptor to its locator and derived text. The original diff remains the readable
review source.

The judge receives the brief and deduplicated findings from the existing review
pipeline, paired with their canonical SHA-256 IDs. Supplying IDs avoids asking a
model to calculate hashes. Critic IDs, provider identities and personas are absent
from the judge projection; arbitrary text already present in a brief/finding is
preserved. There is no chat transcript, memory lookup, tool roster or tool dispatch.
Frozen guidance already incorporated into `Brief.constraints` remains review data.

Provider/model pairs resolve through the explicit model registry, including its
effort fallback. The judge model is selected separately at construction. A system
prompt describes the role and embeds the expected JSON schema. When the resolved
model declares structured-output support, the same recursively strict schema is
also carried by the canonical request and the OpenAI adapter projects it to
Responses API `text.format`. Models without that capability remain prompt-only.
Long input JSON is split into ordered text blocks; their concatenation exactly
reconstructs it. Prompt instructions and provider constraints are advisory and
transport controls, not a sandbox against malicious review content. Deterministic
local validation remains mandatory.

Admission counts the complete canonical model request, including prompt/schema,
block wrappers and output settings, against the resolved input byte budget. Two
independently request-bound byte limits apply: `max_text_output_bytes` bounds the
concatenated UTF-8 answer text, while `max_output` bounds the entire canonical
response, including opaque reasoning, usage and request IDs. The reviewed live
profile uses 8,000 and 64,000 bytes respectively. Reported byte/token usage is also
checked against configured limits, and the 4,096-token/spending ceiling is separate.
These local acceptance checks do not grant spending authority: the existing bounded
transport and spending controller must enforce those limits before dispatch.

Only a completed assistant response containing text and optional reasoning can
produce a result. Text blocks concatenate; reasoning is excluded from the answer.
The strict provider schema removes descriptive titles/defaults, requires every
object property and rejects additional properties. Nullable contract fields are
therefore present as JSON `null`; schema-1 critic schemas omit the schema-2-only
`source_unit` property entirely. The answer must still be exactly one JSON object
with every top-level contract field, an integer schema version of 1, no extra fields
and no duplicate keys at any depth. Typed contract validation enforces nested
fields. Refusal/filtering, truncation, tools, malformed JSON, omitted answers and
budget violations become coarse provider errors. There is one client call per role,
no repair/retry loop, and cancellation propagates to the client. A caller-provided
client must also disable transport retries to preserve the one-exchange spending
contract.

The recursive normalizer treats an object schema with no `properties` member as
an explicit empty object (`properties: {}`, `required: []`, and
`additionalProperties: false`). An object whose `properties` member is present but
is not an object is rejected before a provider request can be prepared. This rule
applies at every nested object node and does not mutate the source schema.

The review pipeline still validates exact quoted evidence, critic/provider quorum,
finding deduplication and judge IDs, then computes the verdict deterministically.
Schema-2 diff evidence must identify one supplied source unit. Validation recomputes
the catalog from the frozen brief and accepts the quote only as an exact substring of
that one raw/before/after view. It performs no whitespace normalization and never
joins hunks. `spec` and `constraints` remain exact source substrings and cannot claim
a diff unit. Schema-1 requests retain their original raw-substring contract so
historical request bytes and outcomes remain stable. New brokered production launch
preparation emits schema 2.
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

For a bounded live retest where the threshold is two critics, use three separately
admitted critic calls and retain the threshold at two. This tolerates one failed or
invalid critic without retrying it. The extra call must be included in the exact
transfer and aggregate spending approvals; redundancy does not create authority or
provider diversity and can still suffer correlated failures.

When one critic fails but the remaining critics meet the sealed quorum, the failure
remains in `ReviewResult.critics`. It does not by itself invalidate a completed
judge verdict or its post-result observation. An `infrastructure_error` verdict,
insufficient quorum, invalid judge evidence, or any signature/runtime mismatch
still prevents observation authentication.

Rollback removes this library adapter and its tests/docs. Existing recorded
packet schemas, run artifacts, terminal commands and provider commands are unchanged.
