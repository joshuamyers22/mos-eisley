# Anthropic Messages integration and conformance

The Claude Messages adapter translates canonical `ModelRequest` and
`ModelResponse` values without exposing Claude wire blocks to the agent or review
contracts. `claude-sonnet-5` and `claude-opus-5-5` are listed as `documented` in the
model registry. Both are available to the brokered review controller. The
[operator-authorized route](OPERATOR_REVIEW.md) uses two exact local approvals and
a $1 ceiling; the older signed campaign retains its separate acceptance gate.

The adapter preserves ordered text, tool calls/results, and complete signed
`thinking` or `redacted_thinking` blocks for subsequent requests. It rejects
foreign or incomplete reasoning blocks, unsupported output content, mismatched
tool stops, missing usage and a response from a different model. Anthropic's
[Messages API](https://platform.claude.com/docs/en/api/messages/create),
[thinking preservation guidance](https://platform.claude.com/docs/en/build-with-claude/extended-thinking),
the [Sonnet 5 model page](https://platform.claude.com/docs/en/models/sonnet-5/overview),
and the [Opus 5.5 model page](https://platform.claude.com/docs/en/models/opus-5-5/overview)
are the current provider references. The adapter uses the official Python SDK
with zero automatic retries, a fixed API origin, disabled environment proxies and
redirects, and a 1 MB decoded HTTP response ceiling.

`mos anthropic-probe` makes one fixed, synthetic, tool-free request to the Sonnet
5 or Opus 5.5 model pinned by its policy after an
existing USD spending policy and ledger pass local preflight. It needs a private
regular key file with no group/other permissions, a fresh output directory and
explicit `--allow-data-transfer`. Its fixed limits are 2,048 input tokens,
128 output tokens, $0.01 per-call policy ceiling, and a full-envelope reservation
before token count or generation. A failed or ambiguous exchange retains the
reservation; a pricing-envelope violation blocks the ledger. It does not retry.

Example setup, with a `SpendPolicy` JSON file that pins the Sonnet 5 model,
reviewed prices and a short UTC validity window:

```sh
mos spend-ledger-create private/anthropic-probe/spend.sqlite \
  --ceiling-microusd 10000
mkdir -m 700 private/anthropic-probe/result
mos anthropic-probe \
  --spend-policy private/anthropic-probe/policy.json \
  --spend-ledger private/anthropic-probe/spend.sqlite \
  --key-file private/anthropic-api-key \
  --output-dir private/anthropic-probe/result \
  --allow-data-transfer
```

The private output contains a reservation, a spending receipt and a metadata-only
probe result. The result records the request and response hashes, provider request
ID, usage and settled cost. It does not retain raw prompt or response content.
The literal false fields state the limits: this one exchange does not prove
provider authorship, invoice reconciliation, review-role behavior, repeated
conformance or evaluation eligibility. These claims require separate evidence.

The review route uses the existing guided envelope, full aggregate reservation,
private worker broker, one-use controller, separate critic and judge approval,
and either signed phase authorization or exact operator approval. Anthropic review
requests are restricted to one
bounded, tool-free user message. They use adaptive thinking at a selected effort,
standard service tier, and nonstreaming Messages calls. A conservative policy
prices cache writes at the documented rate even though the review request has no
cache control. Local runtime records can be handed to an independent observer;
they do not authenticate a live provider response by themselves.

`tests/test_anthropic_review_conformance.py` exercises both signed phases,
brokers, spending settlement, runtime record collection, and observer
authentication with synthetic keys and responses. The test does not grant
production review authorization. The separate operator route is tested with
distinct author, critic and judge model identities and makes no independent
signer claim.

On 2026-09-25, one credentialed Sonnet 5 probe completed with provider request ID
`msg_011CfRHnumLMo3mUgJ2yAjoQ`, 142 micro USD settled, an unblocked ledger and
response hash `b008e1ffeaf2c02d69ac10198efdd82870774d12554c155b6ef4d7992eff6c97`.
Its private receipt remains outside Git. This is connectivity and basic
request/response conformance for the fixed synthetic prompt only.
After the provider-pinned policy was added, a second fresh probe completed with
request ID `msg_011CfRKZJB4Z8ErzFTMjAco1`, response hash
`31df6d25d8454eca767d1d9ad87144753e514133d5daf3003113ce79bc582f17`,
and 142 micro USD settled. Its isolated ledger is unblocked. An earlier local
sandbox attempt in a separate ledger was marked uncertain before token usage was
recorded; that reservation remains intact and is not counted as conformance.
The Opus 5.5 judge-model probe completed with request ID
`msg_011CfRLm79FUvyFj3PasLoiY`, response hash
`bb15594144a0492710b6139e32dc49c700d6667f1f723d48ec3cf255e8a503fe`
and 292 micro USD settled. Its isolated ledger is unblocked. These model probes
establish basic credentialed API behavior, not a credentialed critic/judge run.

On 2026-09-26, the operator-approved live route completed with GPT-6 declared as
author, Sonnet 5 as critic and Opus 5.5 as judge. The frozen source patch covered
22 source/dependency files and had SHA-256
`b8f67d7b01cd5d1f834d159bbd65520f2b8f088e34cf53646c3623087f1ce954`.
The prepared guided brief hash was
`b866f98170321f8b215b21f12dc8c6631079e4403ef89e3bc7ebf63143c45300`.
Both phase approvals were exact; Sonnet returned one finding about adaptive
thinking, and Opus rejected it. The retained `accept` result hash is
`1cb0ce9c8cd8011927434eb193937ab5d660431adb7be7e94f44d09c46f69b35`.
The completed run settled 295,932 micro USD with no unresolved ledger entries.
Three earlier critic attempts failed closed before judge dispatch because their
responses exhausted the output limit or failed the strict JSON/evidence contract.
Their unused judge allowances were reconciled only after verifying the failed
controller terminals and absence of any judge preview or transfer. All four live
review ledgers together charged 826,404 micro USD ($0.826404), below the selected
$1 ceiling, with zero unresolved entries. Private run artifacts remain outside Git.
This is one completed local operator route, without independent signature,
observer, invoice reconciliation or repeated conformance claims.
The [closeout](ANTHROPIC_CONFORMANCE_CLOSEOUT.md) records fresh local verification
and the operator command's separate signed-campaign path. A live signed tranche
remains pending independent enrollment and a new sealed commitment.
