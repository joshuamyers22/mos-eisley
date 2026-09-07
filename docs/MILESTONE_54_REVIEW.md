# Milestone 54 adversarial review: OpenAI conformance campaign commitment

## Disposition

Accepted as a public commitment to the private, deterministic preparation of five
remaining model/effort conformance probes and one shared local spending scope.
Rejected as authority to transfer a blinded brief, make a paid request, retry,
grade, score, promote, or activate a route.

## Committed preparation

On 2026-09-07, separate metadata-only receipts reported exact visibility for
`gpt-5.6-terra`, `gpt-5.6-sol`, and `gpt-6-astra`. Their private receipt hashes are,
respectively:

- `63625c7d38ce6dd94296a64ebb3912e136a7e3fae7c14d9f765b6cdebf27350d`
- `7428cc14741f79fb8c93c947e93fdf66dc526d0f5f64e286114e96bceeaccd04`
- `5f3cb3a0b0d922192b693a275f033d4c856741c00b6fb818ea7f24f34e8860e3`

The private campaign manifest commits to batch
`dc9dbc076e3e55f45b1edc610f6c85f9b70e63ea76cecdc81aff955c423108cb`,
plan `e8ddb3fcaf04422b745f858a575a3dceb90789dc54a45c168250b4b83eeb1411`,
and exactly one probe for each of Terra/medium, Sol/medium, Sol/high, Astra/high,
and Astra/max. For every profile, the selected probe is the lexicographically
smallest blinded sample ID among its 60 assignments. Preparation read the blinded
batch but not the private label map.

The manifest SHA-256 commitment is
`de6cab4d2bc1ad9df7319bf1edd002e3cdeb44596cd8dfc8a4dffb8086665ccc`.
The manifest itself remains private so this public commitment does not create a new
sample-disclosure surface.

A fresh local ledger with identity
`890cd5473e7aad939edeae29a568ce1b44c614a091e4ac5404e96fa422f4467e`
has an immutable 150,000 micro-USD ceiling, zero entries, and zero charged exposure
at sealing. Each probe is capped at 1,000 input and 512 combined visible/reasoning
output tokens. Using current standard rates with no cache discount, the maximum
reservations are 8,144 micro-USD for Terra, 14,240 for each Sol probe, and 35,600 for
each Astra probe: 107,824 micro-USD total with 42,176 micro-USD headroom.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Successful probes are cherry-picked after outcomes are visible | Commit one deterministic sample for every exact profile before any paid campaign result | Git and private-manifest custody are trusted; the public commitment is not an external timestamp service |
| Per-probe policies fragment the advertised budget | Bind every planned maximum to one fresh 150,000 micro-USD shared ledger | Provider activity outside this ledger and ledger rollback remain out of scope |
| Metadata visibility is treated as Responses or billing proof | Preserve readiness receipts with Responses, billing, spend, and routing claims false | Only separately authorized live exchanges test later boundaries |
| Current prices silently become permanent assumptions | Bind exact rates and official per-model sources in the manifest; require fresh expiring spend policies at execution | Provider price changes require a new manifest commitment rather than mutation |
| A 512-token cap is interpreted as a quality judgment | Treat truncation, refusal, or invalid structured output only as conformance evidence | High/max reasoning may consume the cap; the result cannot be scored |
| The campaign commitment itself triggers execution | Set paid request, data transfer, conformance, retry, grading, scoring, promotion, and activation authority to false | Each probe still requires a fresh independent signature and explicit local consent |

## Next gate

For each committed probe, derive a fresh short-lived spend and conformance policy,
review the exact serialized request, obtain a separate independent signature, and
invoke the broker only with explicit local data-transfer consent. Stop after any
uncertain or violating ledger result. Authenticate observations independently and
keep every result non-scoreable. Repeated matrix conformance and separately
authorized failure-boundary probes remain required before calibration conversion.
