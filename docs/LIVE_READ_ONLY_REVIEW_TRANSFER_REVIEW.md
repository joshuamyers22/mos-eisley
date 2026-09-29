# Data-transfer review: live read-only qualification

## Decision and scope

- Accountable operator: Joshua Myers
- Decision date: 2026-09-20
- Scope: the exact OpenAI data boundary used by each sealed critic or judge
  exchange in the three-slot qualification campaign
- Account control: no explicit Zero Data Retention or Modified Abuse Monitoring
  selection was visible for the default project, so this review assumes OpenAI's
  default API retention controls
- Accepted condition: Joshua Myers approved proceeding under that assumption with
  `store: false` and the minimum exact review content
- Exclusions: credentials, local paths, ledgers, signatures, policy prose not selected
  into the brief, repository contents outside the brief, tools, files, images, web
  search, background processing, streaming, conversation state and retries

This record applies the production-template verification and threat-model guidance.
It approves no provider request by itself. The exact sealed request hashes, current
policy windows, dedicated funding, phase signatures and local approval remain
mandatory at every live boundary.

## Provider policy reviewed

The official OpenAI data-controls documentation reviewed on 2026-09-20 states that
API inputs and outputs are not used to train OpenAI models unless the customer opts
in. Under default controls, abuse-monitoring logs may contain prompts and responses
and may be retained for up to 30 days. `store: false` prevents this workflow from
requesting persistent Responses application state, but it does not establish Zero
Data Retention and does not remove the default abuse-monitoring window. Prompt caching
may also keep encrypted GPU-local tensors for up to 24 hours.

Source: <https://developers.openai.com/api/docs/guides/your-data>

## Exact transfer contract

Every critic and judge exchange has two foreground HTTPS operations with zero SDK
retries. Both operations use `https://api.openai.com/v1`, a bounded client that
ignores ambient proxy configuration and does not follow redirects, and a fresh SDK
client. The credential is supplied as authorization metadata by the SDK; it is not
part of either JSON body.

### Input-token count

The input-token count operation receives exactly these JSON fields:

| Field | Exact source or value |
|---|---|
| `model` | The sealed role model ID |
| `instructions` | The fixed critic or judge role plus the complete required response JSON schema |
| `input` | Consecutive user-role text items containing only the canonical role document described below |
| `tools` | `[]` |
| `reasoning` | `{"effort": SEALED_EFFORT}` |
| `parallel_tool_calls` | `true`; inert because `tools` is empty |
| `truncation` | `"disabled"` |

The count body excludes `max_output_tokens`, `store`, `include`, `service_tier`,
`stream` and `background`. Counting transfers the same private instructions and role
document before generation; it is not a local-only operation.

### Response generation

The generation operation receives exactly these JSON fields:

| Field | Exact source or value |
|---|---|
| `model` | The sealed role model ID |
| `instructions` | The same fixed role and required response schema sent for counting |
| `input` | The same canonical user-role text items sent for counting |
| `tools` | `[]` |
| `reasoning` | `{"effort": SEALED_EFFORT}` |
| `max_output_tokens` | The sealed role output cap |
| `parallel_tool_calls` | `true`; inert because `tools` is empty |
| `include` | `["reasoning.encrypted_content"]` for stateless retained reasoning evidence |
| `store` | `false` |
| `truncation` | `"disabled"` |
| `service_tier` | `"default"` |

`stream`, `background`, `previous_response_id`, conversation identifiers, metadata,
remote tools and non-text content are absent. The spending controller rejects added
fields outside its allowlist, nonempty tools, non-text input, non-default service
tier, enabled storage, automatic truncation, streaming or background mode before
contacting the provider.

## Exact role documents

- Critic input is the canonical JSON serialization of `CriticRequest`: exactly the
  frozen `brief` and the selected critic `persona`. Critic IDs, ledger paths, signing
  identities, credentials and other critic outputs are absent.
- Judge input is the canonical JSON serialization of `JudgeRequest`: exactly the
  same frozen `brief` and the verified, deduplicated critic findings. Each finding is
  paired with its locally computed canonical finding ID. Critic identity, persona,
  provider metadata and unverified response text are absent.
- Long canonical JSON is split into consecutive user text items of at most 8,000
  characters. The fixed instruction states that these items concatenate into one
  JSON document and that the document is data, not instructions.

The actual brief, personas, findings, model, effort, output limits and request hashes
are not invented by this record. They become exact only in the reviewed campaign
bundle and, for the judge findings, the separately approved judge preview. Any change
requires a new hash and approval; this decision cannot authorize substitute content.

## Verification and residual risk

Repository tests already prove `store: false`, empty tools, disabled truncation,
text-only spend admission, omitted count-only fields, rejection of storage/background/
streaming/non-text substitutions, and exact critic/judge projections. The final
campaign must additionally inspect the complete preview rather than relying on this
structural inventory.

Residual risk accepted by Joshua Myers: under the assumed default account controls,
OpenAI may retain customer content in abuse-monitoring logs for up to 30 days, and
prompt caching may temporarily retain encrypted tensors. `store: false` is not a ZDR
claim. Stop before dispatch if the payload contains secrets, personal data, unrelated
repository content, hidden tools, files, images, or any field not listed above.

## First campaign outcome

The campaign sealed on 2026-09-20 failed during attempt 1 before a runtime SDK-operation
record or provider response was retained. Therefore this record does not claim that the
count or generation bodies reached OpenAI. Both isolated workers were removed, the
judge and later attempts were not started, and the full attempt allowance remains
conservatively unresolved. A 239-second broker failure is consistent with Keychain
access outliving the 120-second signed phase grant, but that diagnosis remains an
inference until a no-network local credential-access check establishes the boundary.

A separately authorized no-network check later loaded the same Keychain item in
10,695 ms while printing no credential, length or digest. That establishes current
local retrieval readiness only; it does not show that the earlier attempt reached
OpenAI or retroactively identify the original delay.

The next separately sealed campaign did reach OpenAI for both input-token counts, but
both returned `authentication_error`. No generation body or judge request was sent.
The normalized retained error intentionally does not expose provider text or credential
material, so it cannot distinguish an invalid, expired, revoked, malformed,
wrong-project or insufficient-permission key. Both critic charges and the unused judge
allowance remain conservatively unresolved.

After the Keychain password was replaced, a separately authorized minimal
authentication check sent only model `gpt-5.6-luna` and the synthetic text
`credential authentication check` to `POST /responses/input_tokens`. It succeeded
with a count of 9 in 7,678 ms. It made no generation request, carried no provider
storage request, used zero retries and printed no secret data. This proves current
authentication only and grants no campaign authority.

Joshua Myers subsequently granted one single-use exception for one final, wholly new
campaign. The exception changes no transfer field or data-retention decision. It does
not revive either failed campaign or permit reuse of their seals, ledgers, policies,
reservations or process-local signing keys. The final campaign must expose a fresh
exact bundle for sealing before any credential read or provider operation; if it fails,
no replacement campaign is authorized.

The final campaign used a fresh bundle, seal, process key and ledgers. Both critic
token-count and generation operations completed with `store: false` and zero retries.
The provider returned 29,313 total input tokens (29,307 cache-write tokens) and 2,161
total output tokens across the two critics. Locally canonicalized responses were 8,221
and 8,617 bytes, exceeding the sealed 4,000-byte response ceiling; both completions
therefore failed before critic evidence could satisfy quorum. No judge request,
observation, later attempt or launch occurred. Both isolated containers were removed.
The exception is consumed, the qualification is stopped, and no replacement campaign
is authorized.
