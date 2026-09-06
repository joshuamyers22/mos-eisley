# Milestone 42 adversarial review: OpenAI billing collector

## Disposition

Accepted as a private, explicit-consent collector and strict parser for bounded OpenAI
Admin API aggregate evidence. Rejected as proof that the daily API-key scope was
exclusive, as exact response-level billing attribution, or as a no-network operation.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| The collector inherits a proxy, follows a redirect, retries, or streams an unbounded body | Use the official SDK through the existing bounded client with `trust_env=false`, redirects and streaming disabled, zero automatic retries, a 60-second timeout ceiling, and a one-megabyte decoded-body cap per page | SDK, HTTP/TLS stack, DNS, OpenAI, and host networking remain trusted |
| A sensitive account read happens before consent | Check `--allow-account-billing-read` in main dispatch before reading files, environment credentials, or constructing transport | The operator and organization-key scope remain trusted |
| Validation fails only after a billable model call | The collector has no model transport; closed-window, identifier, policy, output, and lineage checks precede Admin reads | Admin reads themselves are real provider requests |
| A partial cursor chain appears complete | Require coherent `has_more`/`next_page`, reject repeated cursors, cap at 20 pages, and require a terminal page | Provider omission inside an otherwise valid response is not independently detectable |
| Replayed cost rows inflate or cancel a total | Require one exact daily bucket and reject duplicate project/API-key/line-item groups before exact microusd reduction | Legitimate provider schema expansion may fail closed until reviewed |
| Float conversion rounds a near match into success | Convert the SDK JSON number through decimal text and reject any total below integer-microusd precision | Provider aggregates with finer precision will be unreconcilable rather than rounded |
| Raw identifiers or the Admin key leak into console or portable evidence | Store raw pages only in a new mode-0600 private file; print digests and booleans; never serialize the credential | Raw private evidence intentionally contains account identifiers; same-UID and backup access remain sensitive |
| One usage result is called exclusive daily API-key use | Rename the verified fact to one completion request in the usage bucket and structurally set daily exclusivity and exact response-cost attribution to false | Derivation still depends on a separately recorded operator exclusivity attestation |
| A collection silently changes accounting or authorizes another call | Fix ledger mutation, automatic release, model inference, retry, signing, quality, promotion, and activation outside collector authority | Manual financial and credential operations remain external |
| A valid collection is paired with another local result | Reauthenticate conformance and publication before collection, bind model and windows, then revalidate the bundle and require exact local token/cost equality during derivation | Local store rollback/cloning and trusted parser behavior remain in the trust base |

## Verification status

Fixture-backed tests exercise official-SDK URL/query/header behavior, client closure,
pagination failures, scope substitution, multiple requests, malformed windows,
sub-microusd values, credential/console non-disclosure, pre-consent ordering, immutable
output, and collection-to-observation derivation. No paid model request or real Admin
API read was made. A separately authorized real conformance exchange and account read
are still required before operational claims.
