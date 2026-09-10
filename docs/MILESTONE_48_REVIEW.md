# Milestone 48 adversarial review: OpenAI model readiness

## Disposition

Accepted as a narrow, operator-triggered check of credential authentication and
exact model visibility. Rejected as billing readiness, Responses conformance,
generation success, quality evidence, or downstream authority.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A readiness check silently sends a prompt | Fix the request to `GET /models/gpt-5.6-luna`; transfer no prompt or generation payload | The API key and model ID still reach OpenAI |
| Model selection turns the probe into an arbitrary provider browser | Expose no model override; require exact returned ID and `object=model` | A code release is required to change the target |
| A metadata success is treated as Responses or billing proof | Persist literal denials for Responses access and billing verification | Only a separately authorized canary and later billing evidence can test those boundaries |
| A receipt activates routing before empirical evaluation | Fix grading, scoring, promotion-equivalent routing activation, and spend authority to false | Consumers must continue to reject this distinct schema |
| SDK retries turn one operator action into several requests | Configure `max_retries=0` and test exactly one transport call for success and every failure class | A remote service may internally process an accepted request more than once |
| Provider errors leak credentials or account details | Reuse the fixed failure vocabulary and persist no messages, bodies, headers, or request IDs | Trusted process memory and the official SDK remain in scope |
| A stale or overwritten result obscures the attempted check | Require an existing parent and create one fresh mode-0600 receipt exclusively | Local same-UID rollback or deletion needs external retention to detect |
| “Metadata-only” is advertised as guaranteed free | Grant no spend authority and make no pricing claim for the lookup | Provider billing and policy can change externally |

## Verification status

Synthetic official-SDK tests cover exact success, authentication, permission, quota,
rate limit, not found, invalid request, transport, timeout, mismatched metadata,
raw-error non-disclosure, one-attempt behavior, consent/key ordering, and exclusive
private output. Automated tests make no live provider request.
