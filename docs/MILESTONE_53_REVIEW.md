# Milestone 53 adversarial review: registry-bound model readiness

## Disposition

Accepted as a widening of the metadata-only readiness check from one fixed model to
one explicitly selected model in Mos Eisley's reviewed OpenAI registry. Rejected as
arbitrary provider discovery, Responses access, billing or quota proof, conformance,
quality evidence, campaign admission, or routing authority.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A model argument becomes an arbitrary authenticated provider browser | Argparse and the provider boundary accept only exact IDs in `openai_registry()` | Changing the reviewed code release changes the allowlist |
| A registry entry is confused with live account access | Create one fresh per-model receipt containing only `visible` or an allowlisted failure | Visibility is credential-, project-, time-, region-, and provider-dependent |
| The provider or a substituted probe returns metadata for a nearby model | Require `object=model`, exact returned ID, and CLI requested/receipt equality | The official SDK, TLS, provider, and local process remain trusted |
| Multiple selected models silently become a batch or retries | Preserve one command, one model, one GET, and zero SDK retries | Operators must explicitly invoke and acknowledge each lookup |
| Metadata visibility authorizes the paid campaign | Preserve literal denials of generation, spend, billing, Responses verification, grading, scoring, and activation | Separately signed conformance and spending controls remain mandatory |
| A failure leaks account or provider details | Preserve the allowlisted failure kind/detail vocabulary and discard raw messages, bodies, headers, and IDs | Process memory and same-UID access remain trusted |
| Existing automation changes behavior unexpectedly | Keep `gpt-5.6-luna` as the default when `--model` is omitted | Callers relying on help text should review the widened explicit option |

## Verification scope

Synthetic official-SDK tests cover every registered OpenAI model, exact GET paths,
empty request bodies, exact response identity, unknown-model rejection before key
access, cross-model substitution, one-attempt behavior, and all pre-existing safe
failure and non-authority properties. Automated tests make no provider request.
