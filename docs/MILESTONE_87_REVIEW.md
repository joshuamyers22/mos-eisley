# Milestone 87 adversarial review: complete-batch campaign commitment

## Disposition

Accepted as an offline, content-addressed commitment to the 342 assignments not
already represented by the reviewed partial seed. Rejected as execution authority,
a spend reservation, expected cost, complete calibration, grading or scoring
authority, quality evidence, promotion, routing activation, or permission to retry.

## Retained result

The public policy pins plan
`e8ddb3fcaf04422b745f858a575a3dceb90789dc54a45c168250b4b83eeb1411`,
batch `dc9dbc076e3e55f45b1edc610f6c85f9b70e63ea76cecdc81aff955c423108cb`,
and partial seed
`c67dfcfac073ba4946afd59b2f2960fb9de10740654cdaf8ad1183f91e8cf570`.
Its canonical SHA-256 is
`298ea713382f2babf6d54425610250181c69a623b84443c52bff836b76fab69e`.

The real planner ran with both supported OpenAI key variables absent. Its private
163,736-byte canonical manifest has SHA-256
`822168cda36e4e3165e0957317d347c421f086e815a7acf32a5d2490502a3ee1`.
It records 342 pending assignments, exactly 57 in each of six profiles, and a
15,377,973-micro-USD worst-case envelope. It contains no blinded request content and
performed no credential access, reservation, provider call, grading, or scoring.

## Adversarial findings

| Attack or ambiguity | Disposition | Remaining boundary |
| --- | --- | --- |
| The 18 probes are accidentally scheduled again | Reverify every seed request against the frozen batch and subtract those exact sample IDs | The future executor must accept only a manifest-listed pending assignment |
| A route or request is swapped after planning | Bind candidate, request, sample, profile-plan, batch, seed, policy, and sequence digests | Host and retained-file custody remain trusted |
| Hashes leak blinded briefs | Store request hashes and route identities only; keep the manifest private | Low-entropy external briefs could still be guessed and require separate confidentiality controls |
| A budget envelope is treated as permission to spend | Fix credential access, reservation, request, retry, grading, scoring, promotion, and activation to false | Fresh independent authority and explicit local transfer consent remain mandatory per attempt |
| Current rates become stale during a long campaign | Timestamp official-source rate checks and require a future paid boundary to recheck them | A rate change requires a new reviewed commitment rather than silent budget inflation |
| Cache writes cost more than ordinary input and understate the maximum | Price all input at the higher 1.25× cache-write rate and assume no cached-input discount | The live spend controller must add cache-write reservation and settlement support before execution |
| Discounted Batch, Flex, or fast pricing changes accounting | Authorize only default service tier; deny Batch API and fast mode | Alternative service modes require their own policy and conformance |
| A 1,000-token input or output cap is insufficient | Require fail-closed pre-send token counting and preserve terminal failures | Changing caps or retrying needs new authority; the planner cannot improve coverage itself |
| Execution order adapts to observed model quality | Preserve all 342 entries in frozen batch order and fixed-matrix semantics | Operational scheduling may pause, but cannot select, drop, or reorder evidence based on outcomes |

## Gate effect

The complete-batch campaign is now deterministically planned, but none of it is
authorized to run. Next, derive and authenticate a short-lived, one-use execution
decision for one exact manifest assignment, with a fresh time-bounded spend policy,
current-rate equality, cache-write-aware shared-ledger admission, explicit transfer
consent, and terminal failure retention. Only after that boundary is reviewed should
the 342 paid assignments begin.
