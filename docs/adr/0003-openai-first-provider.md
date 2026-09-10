# ADR 0003: OpenAI Responses as the first live provider

Date: 2026-09-05. Status: implemented as a preview; exact-profile live-conformance
gate passed 2026-09-09; calibration and runtime activation pending.

## Decision

Implement OpenAI first through the official asynchronous Python SDK and Responses
API. Use `gpt-6-astra` as the initial registry model because the current
[OpenAI model guide](https://developers.openai.com/api/docs/guides/latest-model)
recommends it for complex reasoning and coding. The
[model page](https://developers.openai.com/api/docs/models/gpt-6-astra) documents
function calling, structured output, reasoning efforts `low`, `medium`, `high`,
`xhigh` and `max`, a 1,050,000-token context window and 128,000 maximum output.
Mark these capabilities `documented`, not `live_conformance`, until a credentialed
test confirms account access and round-trip behavior.

Keep provider tokens separate from canonical serialized-byte limits. The first
live command limits input-file reads to 64,000 bytes, output to 4,096 provider
tokens, model iterations to one and tool calls to zero. The larger documented model
limits describe capability; they are not the operational defaults.

Translate the canonical protocol to Responses input items and back. Function tools
use `strict=true`; every property is required and every object rejects additional
properties, matching the
[function-calling guide](https://developers.openai.com/api/docs/guides/function-calling).
Preserve provider call IDs separately from bounded harness IDs. Request encrypted
reasoning content and carry the validated raw reasoning item forward for stateless
tool turns.

Set `store=false`, disable truncation, disable SDK retries and retain Mos Eisley's
outer request deadline. Require `OPENAI_API_KEY` from the process environment and
an explicit `--allow-data-transfer` flag. Never serialize the key. Write config,
full canonical responses, aggregate token usage and the fsynced boundary journal
to a manifest-completed private run directory.

## Consequences

The adapter can be tested deterministically with captured response shapes and can
make a deliberately narrow live request when the operator opts in. The existing
recorded critic/judge workflow remains offline, so this does not yet produce a live
adversarial verdict. Live artifacts are inspectable but cannot reproduce a model
execution.

The SDK receives an HTTP body before Mos Eisley applies its canonical byte ceiling.
Provider retention still follows organization and OpenAI policy despite
`store=false`. Model access may vary by account. Dollar budgeting, independent
transport byte limits, retry policy, live quality evaluation and credentialed
conformance remain required before production use.

## 2026-09-07 evaluation amendment

The documented OpenAI registry also includes `gpt-5.6-sol`, `gpt-5.6-terra`, and
`gpt-5.6-luna` as non-default evaluation candidates. All three expose the Responses
API, structured outputs, function calling, a 1,050,000-token context window, a
128,000-token output limit, and reasoning efforts `none`, `low`, `medium`, `high`,
`xhigh`, and `max`; their documented default is `medium`. Astra remains the runtime
default. Adding candidates does not activate routing or establish account access:
those decisions still require blinded evaluation, live conformance, and the existing
promotion controls.

## 2026-09-09 conformance amendment

The frozen six-profile exit gate has passed after three qualifying authenticated
successes per exact model/effort profile, five installed-wheel failure boundaries,
and a lineage-wide offline aggregate review. This establishes conformance only for
Luna/low, Terra/medium, Sol/medium, Sol/high, Astra/high, and Astra/max through the
bounded zero-retry broker path. It does not generalize to every documented effort or
feature and does not prove provider authorship, billing, or model quality. A separate
calibration converter and the existing scoring, holdout, promotion, and activation
controls remain mandatory before empirical routing or production use.

The first separately reviewed converter is intentionally partial. It binds the exact
aggregate report and 18 qualifying sources into a distinct 18-of-360 calibration
seed while refusing provider credentials. It does not issue `RawResultSet` or grant
grading, scoring, promotion, activation, or additional-request authority. Full batch
execution and a later gradeable issuance boundary remain mandatory.
