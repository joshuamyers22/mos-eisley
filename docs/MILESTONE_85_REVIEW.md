# Milestone 85 adversarial review: OpenAI live-conformance aggregate gate

## Disposition

Accepted as completion of the frozen OpenAI live-conformance exit gate and as
permission to design a separate calibration converter. Rejected as provider
authorship proof, billing reconciliation, a quality claim, calibration conversion,
grading, scoring, promotion, routing activation, production readiness, or authority
for another provider request.

## Aggregate evidence

The offline aggregate compiler refused to run while either supported OpenAI key
variable was present. It accessed no credential and sent no provider request. Its
private 32,624-byte, sorted compact JSON report has SHA-256
`e58dc274b5087271fe1f241724fdd1f319956b4fffba8bf1e83e086db26ea72a`.
The report records `outcome=pass`, all 23 required execution positions, and literal
false provider-authorship, billing, quality, complete-batch, conversion, grading,
scoring, promotion, activation, and additional-request claims.

The compiler did not trust saved success receipts as summaries. It reauthenticated
all 20 retained successful exchanges at their original authentication timestamps
against the frozen batch, exact conformance policy, independent observer signature,
assignment authorization, compiled artifact, broker audit, and current immutable
ledger entry, then required the recomputed receipt to equal the retained receipt.
Every sample, receipt, signature, artifact, authorization, outcome, provider request,
provider response, and ledger-entry identity is distinct.

Exactly 18 successes qualify:

| Profile | Qualifying positions |
| --- | --- |
| `gpt-5.6-luna` / `low` | `luna-low-1`, `luna-low-2`, `luna-low-3` |
| `gpt-5.6-terra` / `medium` | `terra-medium-1`, `terra-medium-2`, `terra-medium-3` |
| `gpt-5.6-sol` / `medium` | `sol-medium-1`, `sol-medium-2`, `sol-medium-3` |
| `gpt-5.6-sol` / `high` | `sol-high-historical-1`, `sol-high-2`, `sol-high-3` |
| `gpt-6-astra` / `high` | `astra-high-1`, `astra-high-2`, `astra-high-3` |
| `gpt-6-astra` / `max` | `astra-max-1`, `astra-max-2`, `astra-max-3` |

The report separately retains and excludes the two earlier authenticated Astra/high
successes invalidated by the sequence-10 break. Qualifying local settlements total
135,812 micro-USD; the two excluded successes total 43,750 micro-USD. These are
local pricing-controller results, not reconciled provider charges.

The `historical` label on the first Sol/high position identifies its earlier
campaign, not exclusion: its record has `qualifying=true` and that profile had no
intervening failure. Only records with `qualifying=false` are excluded.

The three committed campaign manifests rehash to
`de6cab4d2bc1ad9df7319bf1edd002e3cdeb44596cd8dfc8a4dffb8086665ccc`,
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8`,
and `df66aba92b145d243bf3cb5b378ec477ea81adafcf072286a250078b8f44b885`.
The initial, v1, v2, and v3 success ledgers contain respectively 2, 5, 10, and 5
settled entries, no unresolved entries, and no pricing violation. The initial
ledger's 453 micro-USD is completely explained by the 14-micro-USD synthetic canary
and 439-micro-USD first Luna success. V1, v2, and v3 contain 45,424, 83,439, and
80,110 micro-USD respectively. V2 includes the separately retained 29,850-micro-USD
terminal validation failure.

## Exact attempt coverage

The aggregate retains the v2 sequence-10 terminal artifact
`14b9645482e7689bff521c459b2bdb7a2e83ece870800afa0684cfb8f741fa4d`
as a non-scoreable `invalid_response` / `validation` result and confirms that v2
sequences 11 and 12 remain committed but unexecuted after the mandatory stop. It
also records two expired unsigned preparations as no-send events.

The first v3 sequence-1 invocation remains a `prepared` missing-image stub with no
admission, outcome, reservation, receipt, or container lifecycle. Its preparation
summary records an empty ledger before the invocation and hashes to
`230c5aa47c1227c3ecf50ba94a89976c2351c7db45cd18b1706a2db3b0f4e881`.
The corrected replacement deliberately reused the same deterministic ledger entry
identity under a different spend policy, so the current ledger now shows that later
settlement. The aggregate binds that settlement to the successful replacement and
does not misstate the historical stub as currently absent.

All five boundary verification records and their authoritative audit/ledger sources
were rechecked. Their verification-record hashes are:

| Boundary | Verification SHA-256 | Retained ledger disposition |
| --- | --- | --- |
| F1 | `6878169e6abca21fcd3129b5a8f592ad470ae2ba048c6cd8185549357a95b6f8` | empty |
| F2 | `99dcf6ac783cdfa7b887ad97208eb77e4275e10e5c431738ef46978e2f2e6a14` | empty |
| F3 | `b093171fc65f1234ea406ba14d602ee45369276654e8261c5891e08541d4b768` | 635 micro-USD uncertain |
| F4 | `bf066fcafe26749b412068aaf613f2b30895ae31e9dcb00b1a39556f4c367935` | 44 micro-USD settled |
| F5 | `113d704d01741627421cad4ba9e203c76701a4e10ce15f4fdae1b0171837f613` | 635 micro-USD held |

The unresolved F3 and F5 entries are required conservative evidence in disposable
failure ledgers. They are not defects in a success ledger and must never be released,
retried, reset, or reused.

## Adversarial findings

| Attack or ambiguity | Disposition | Remaining boundary |
| --- | --- | --- |
| Counting only the final 18 hides the failed streak | Reauthenticate all 20 successes and explicitly exclude the two invalidated Astra/high records | Provider activity outside these campaign paths remains out of scope |
| A saved authenticated receipt substitutes for source verification | Recompute each receipt from policy, signature, batch, artifact, audit, authorization, and ledger | Host and retained-source custody remain trusted |
| Settled entry count hides an unexplained request | Bind every success entry, the canary entry, and the v2 failure; require exact ledger cardinality and cost | Separate activity outside the four local ledgers is not excluded |
| The v3 pre-dispatch entry appears settled today | Bind the settlement to the later different-policy replacement and prove the stub from no admission/outcome/lifecycle plus its historical empty snapshot | The historical snapshot is locally retained evidence, not an external monotonic witness |
| Controlled uncertain/held ledgers are called a gate failure | Keep them permanently isolated and require success ledgers alone to have no unresolved entries | Manual filesystem or SQLite tampering remains in the local trust boundary |
| Twenty-three executions silently grant calibration or routing authority | Fix conversion, grading, scoring, promotion, activation, and new-request authority to false | A distinct reviewed converter is the next eligible design step |
| The aggregate cost is presented as an OpenAI bill | Label every amount as local controller accounting and keep billing reconciliation false | Provider billing collection and reconciliation remain separate |

## Gate effect

The frozen OpenAI live-conformance exit gate is complete. This changes only the
prerequisite state: a separately reviewed, offline converter may now be designed to
turn the 18 qualifying authenticated records into calibration input. No conversion
has occurred, no model quality has been measured, and routing remains disabled until
the later calibration, holdout, promotion, and activation gates pass.
