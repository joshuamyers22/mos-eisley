# Dependency batch 260–263 verification

- Status: active; final gate and accountable provider review pending.
- Owner: repository maintainer.
- Started (UTC): 2026-10-03.
- Related PRs: #260 sse-starlette, #261 Starlette, #262 Ruff, #263 Anthropic SDK.

## Objective and completion evidence

Integrate the four dependency heads after #259 (Hatchling) while preserving the
Anthropic provider's fixed origin, zero retries, disabled environment proxies and
redirects, timeout, decoded response ceiling, and spending admission. Keep the
exported runtime requirements aligned with `uv.lock`. Resolve the unrelated `/diff`
mouse-render timing failure seen in #261 and #262 CI without weakening its exact
selected-line assertions. Completion requires focused transport and terminal tests,
lint, strict typing, export verification, container smoke, one full `make check`,
final-head CI, and accountable owner review of the provider SDK change.

Selected guidance: [Python engineering](PYTHON_ENGINEERING_GUIDE.md),
[bounded verification](AGENTIC_VERIFICATION_GUIDE.md),
[Anthropic provider contract](ANTHROPIC_PROVIDER.md),
[provider transport threat model](G4_ANTHROPIC_REVIEW_TRANSPORT_THREAT_MODEL.md),
and [work-note template](../templates/WORK_NOTE.md).

The batch is an integration and compatibility repair. It grants no live provider
spend, credential access, model activation, Windows qualification, or release
authority. No live provider calls are part of verification.

## Observations and corrections

| Finding | Evidence | Correction | Verification |
|---|---|---|---|
| #261 and #262 source CI intermittently raised `KeyError` for a `/diff` mouse coordinate | Their source jobs failed in `test_mouse_range_selects_exact_hunk_lines`; #254 and #258 passed the same test | Wait for both exact rendered coordinates before sending mouse events | Focused acceptance test passed; final CI pending |
| #263 SDK 1.10 no longer installs `httpx`; the provider's bounded client imported and subclassed that package | #263 source typing and container CLI import failed | Use `httpx2` types for the existing bounded client, matching the [SDK migration guide](https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md); retain the response ceiling and zero retries | SDK client construction, one synthetic no-network SDK request through the bounded client, oversized-response refusal, and container smoke passed |
| Bot requirement updates did not update the transitive versions in `uv.lock` | Merged heads selected sse-starlette 3.5.0 and Starlette 1.7.0 only in the runtime export | Resolve both versions in `uv.lock`, then regenerate the export from that lock | `verify-export`, lint, typing, and focused tests passed |

The final integrated tree must keep Hatchling 1.32.4, Ruff 0.16.9,
sse-starlette 3.5.0, Starlette 1.7.0, and Anthropic 1.10.0. The SDK's change to
`httpx2` is an implementation boundary, not a reason to restore unused `httpx`.
The transport still rejects streaming and responses over its configured byte cap.
The existing owner-operated authorization and conservative spending ledger remain
the authority for any later live call.

## Handoff

- Current state: all four bot heads are ancestors of the integration branch;
  the corrected lock/export and focused checks are passing.
- Next action: finish container and full local gates, run final-head CI, then obtain
  accountable owner review for the exact provider SDK candidate before merge.
- Recovery: revert the integrated dependency merge if the final gate or owner review
  blocks it; keep old provider behavior on `main` until accepted.
