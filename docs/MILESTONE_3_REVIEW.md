# OpenAI provider preview adversarial review

Date: 2026-09-05. Scope: OpenAI registry entry, Responses translation, opt-in live
command, token accounting and live artifact store. Reviewer: implementing assistant
self-review; no credentialed request or independent model review was performed.

Disposition: suitable for review and an operator-approved conformance request. It
is not production-ready and does not yet run the critic/judge pipeline live.

## Findings and corrections

| Impact | Finding | Correction / evidence |
|---|---|---|
| High | Treating token counts as bytes would create false budget guarantees | Separate usage units and model token capabilities from local byte ceilings |
| High | A live command could send source merely by being invoked | Require a named file, environment key and explicit data-transfer acknowledgement |
| High | Responses storage defaults could retain avoidable server-side state | Send `store=false` on every request and test the exact payload |
| High | Raw provider IDs can violate harness identifier bounds | Preserve native call ID and derive a bounded deterministic harness ID when needed |
| High | Reconstructed reasoning could lose required provider state | Request encrypted reasoning and preserve the whole validated reasoning item |
| Medium | Best-effort tool arguments weaken canonical validation | Require OpenAI strict schemas and reject optional canonical properties |
| Medium | SDK retry timing could outlive the controller's deadline assumptions | Construct the live SDK with zero retries and retain the outer asyncio deadline |
| Medium | A valid manifest could contain internally inconsistent live artifacts | Cross-check provider/model, turn prefix, usage, response count and journal hashes |
| Medium | API errors or rejected values could expose credentials/content | Wrap provider errors and retain generic CLI diagnostics; regression-scan artifacts |
| Low | Model documentation could be mistaken for tested account capability | Registry marks OpenAI as `documented`; conformance is a distinct state |

## Verification

- Ruff lint/format and strict Pyright: passed.
- Unit/integration/architecture suite: 58 tests passed; 92% combined statement and
  branch coverage before final delivery checks.
- Captured two-turn shape exercises strict function call, fixture result, encrypted
  reasoning carry-forward, final text, token usage and live artifact verification.
- CLI tests prove consent and credential checks happen before prompt-file access and
  that a credential is absent from completed artifacts.

## Remaining work

No credentialed request has verified actual account access or the current SDK/API
round trip. The SDK buffers the response before canonical byte validation. There
is no dollar budget, price snapshot, retry/backoff policy or live review fan-out.
The live CLI exposes no tools; adapter tool handling is covered only by captured
contract tests. Provider-side data controls remain external to Mos Eisley.

Next review trigger: credentialed conformance or wiring OpenAI into critic/judge.
