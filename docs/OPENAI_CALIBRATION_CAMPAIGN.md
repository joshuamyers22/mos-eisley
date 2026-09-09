# Offline OpenAI calibration campaign planning

`eval-plan-openai-calibration-campaign` commits the exact unexecuted remainder of
the frozen calibration batch without accessing a credential, reserving money, or
authorizing a provider request. It consumes the 360-assignment blinded batch, the
reviewed 18-assignment partial seed, and the public campaign policy.

The committed
[`openai-calibration-campaign-v1.json`](../policies/openai-calibration-campaign-v1.json)
policy binds the exact plan, batch, seed, six model/effort profiles, token ceilings,
standard per-token rate assumptions, and a worst-case aggregate ceiling. The rates
were checked against the official OpenAI model pages on 2026-09-09. The envelope
uses the higher 1.25× cache-write input rate for every input token and takes no
cached-input discount. Batch API, Flex, and fast mode are not authorized.

Rate sources: [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), and
[GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra).

| Profile | Remaining | Input cap | Output cap | Maximum each |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` / `low` | 57 | 1,000 | 512 | 865 micro-USD |
| `gpt-5.6-terra` / `medium` | 57 | 1,000 | 512 | 8,644 micro-USD |
| `gpt-5.6-sol` / `medium` | 57 | 1,000 | 512 | 15,240 micro-USD |
| `gpt-5.6-sol` / `high` | 57 | 1,000 | 512 | 15,240 micro-USD |
| `gpt-6-astra` / `high` | 57 | 1,000 | 2,048 | 114,900 micro-USD |
| `gpt-6-astra` / `max` | 57 | 1,000 | 2,048 | 114,900 micro-USD |

The aggregate maximum is 15,377,973 micro-USD ($15.377973). This is an arithmetic
upper envelope, not expected cost, a reservation, an OpenAI billing claim, or
permission to spend. A future paid boundary must support cache-write usage in its
reservation and settlement logic, recheck current pricing, and fail closed if the
pinned assumptions are stale.

```console
env -u OPENAI_API_KEY -u MOS_OPENAI_KEY \
  mos eval-plan-openai-calibration-campaign \
  --batch .mos-eisley/eval/calibration-batch.json \
  --calibration-seed private/openai-live-conformance-gate-v1/calibration-seed.json \
  --campaign-policy policies/openai-calibration-campaign-v1.json \
  --output private/openai-calibration-campaign-v1/manifest.json \
  --allow-offline-planning
```

The private manifest contains sequence numbers, frozen batch positions, sample,
candidate, request and profile-policy hashes, model/effort identities, and maximum
costs. It does not embed any brief, response, critique, label, grading material,
credential, reservation, or executable capability. Every assignment keeps
execution, retry, grading, scoring, promotion, and activation authority false.

The command refuses either supported OpenAI key variable, requires explicit offline
acknowledgement, rejects output/input overlap, writes exclusively with mode `0600`,
and proves exactly 57 unseeded requests in each profile in original batch order.
The next boundary must derive short-lived, independently signed authority for one
exact manifest assignment while preserving a terminal record for every attempt.
