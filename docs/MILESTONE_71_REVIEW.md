# Milestone 71 adversarial review: replacement Astra campaign commitment

## Disposition

Accepted as a public commitment to five private, deterministic, unexecuted Astra
live-conformance attempts. Rejected as authority to access a credential, transfer a
blinded brief, reserve or spend money, contact OpenAI, continue campaign v2, retry,
grade, score, promote, convert calibration data, or activate routing.

## Committed recovery campaign

The private campaign manifest remains bound to blinded batch
`dc9dbc076e3e55f45b1edc610f6c85f9b70e63ea76cecdc81aff955c423108cb`
and plan `e8ddb3fcaf04422b745f858a575a3dceb90789dc54a45c168250b4b83eeb1411`.
It also binds the halted v2 manifest
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8`
and terminal sequence-10 failure artifact
`14b9645482e7689bff521c459b2bdb7a2e83ece870800afa0684cfb8f741fa4d`.
Those inputs preserve 15 historical authenticated successes, 13 current qualifying
successes, and the reset Astra/high streak.

The five requests are ordered as three `gpt-6-astra` / `high` replacement-streak
positions followed by the two remaining `gpt-6-astra` / `max` positions. For each
exact profile, the selector takes the required number of lexicographically smallest
sample IDs absent from both the six pre-v2 authenticated successes and every v2
commitment. This excludes the failed sequence-10 sample and does not recycle unused
v2 sequences 11 and 12. The five selected IDs are unique and remain private. Target
ordinals describe required future consecutive positions, not successful outcomes.
Any non-success stops this campaign.

## Output-limit and budget disposition

OpenAI documents `max_output_tokens` as a ceiling covering visible output and
reasoning tokens, and the official Astra model page lists a 128,000-token maximum
output plus standard input/output rates of $10/$50 per million tokens. Sources were
checked on 2026-09-08: the
[Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
and [Astra model page](https://developers.openai.com/api/docs/models/gpt-6-astra).

Prior valid Astra/high results used 283 and 439 combined output tokens. The next
attempt consumed exactly its 512-token ceiling and failed strict response validation;
its end-to-end latency was 18,437 ms. The replacement campaign therefore commits a
2,048-token combined output ceiling and 60-second request timeout. The output ceiling
is four times the failed limit and more than 4.6 times the largest prior valid
Astra/high observation; the timeout is more than three times the failed attempt's
latency. These are bounded recovery margins, not quality claims or permission to
generate more content than the critique schema requires.

Every request remains capped at 1,000 input tokens. At the committed standard rates,
each maximum is 112,400 micro-USD and the five-request worst case is 562,000
micro-USD. A fresh ledger with identity
`771cc6fcb438d44cbe2f51502bce2c9adc20bd26a89aa25fa17d57321c0ca9c6`
has an immutable 600,000 micro-USD ceiling and 38,000 micro-USD headroom. It had zero
entries, zero charged exposure, no unresolved entries, and was unblocked at sealing.
The private manifest SHA-256 commitment is
`df66aba92b145d243bf3cb5b378ec477ea81adafcf072286a250078b8f44b885`.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| The failure is hidden by continuing v2 | Bind the v2 manifest and terminal failure, prohibit v2 continuation, and use a distinct ledger and campaign | Private artifact custody and host execution remain trusted |
| Stale or cherry-picked samples enter the replacement | Exclude all prior success and v2 commitment IDs, then use an exact lexical rule before any new outcome | Git is not an external timestamp service, and private-manifest custody remains trusted |
| Earlier Astra/high successes survive the broken streak | Start three new high ordinals at one and execute them before max | Any new non-success resets the high streak and halts the campaign |
| The first Astra/max success is discarded or overstated | Retain exactly one qualifying max success and commit only positions two and three | Both new max results still require independent authenticated success |
| A larger output cap is presented as guaranteed validity | Treat 2,048 as a bounded truncation margin; strict critique validation remains unchanged | Another invalid, refused, or truncated response halts the campaign |
| Higher caps conceal spend growth | Bind exact token caps, rates, per-call maxima, aggregate maximum, and one fresh 600,000 micro-USD ledger | Provider activity outside this ledger and ledger rollback remain out of scope |
| A 60-second timeout weakens execution bounds | Keep the CLI's maximum allowed timeout, no retries, and stop on any timeout | Longer latency can still fail naturally and consume provider-side resources |
| Sealing is treated as execution consent | Fix credential, transfer, reservation, send, conformance, retry, grading, scoring, promotion, and activation authority to false | Every request requires fresh short-lived policy, independent signature, and explicit local consent |

## Next gate

Prepare only sequence 1 without provider access. The operator must inspect the exact
bounded authorization, sign independently, and provide explicit local data-transfer
consent before its one permitted request. Authenticate a successful observation
before preparing sequence 2. Any non-success halts campaign v3. Even five successful
results complete only the 18-result live matrix; the five frozen failure-boundary
tests and all later calibration, holdout, promotion, and activation gates remain.
