# Work Note: review response-envelope budget correction

- Status: complete
- Owner: Josh Myers
- Started (UTC): 2026-09-20
- Last updated (UTC): 2026-09-20
- Review or delete by: completion or abandonment of Q-004
- Related issue/incident/ADR: qualification finding Q-004;
  `docs/REVIEW_RESPONSE_BUDGET_INCIDENT.md`

## Objective and completion evidence

- Intended outcome: allow a bounded canonical review response to retain opaque
  encrypted reasoning without weakening the smaller visible JSON-answer limit.
- Required invariants: provider output-token and spending ceilings do not increase;
  visible answer text remains bounded; the complete canonical response remains
  bounded; response limits remain frozen into the exact model request; oversized
  text or envelopes fail closed without retry; old campaign evidence is unchanged.
- Evidence that will show completion: focused boundary tests reproduce the failure
  class and pass after the correction; review/broker/evidence tests pass; the full
  quality and container gates pass; an adversarial review finds no open blocker.

## Context retrieved

- `AGENTS.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, `docs/ROADMAP.md` G2
- `docs/PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md`
- `docs/PYTHON_ENGINEERING_GUIDE.md`
- `docs/AGENTIC_VERIFICATION_GUIDE.md` and its verification-loop template
- threat-model, incident-review, work-note and adversarial-review templates
- `src/mos_eisley/core/budget.py`, `core/protocol.py`,
  `providers/model_reviewer.py`, `providers/brokered_openai.py`
- protocol-budget, model-reviewer, brokered-client and conformance-acceptance tests
- final-campaign retained size/accounting evidence recorded in the qualification note

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-20 | observation | The review policy allowed 4,096 provider output tokens but used the 4,000-byte low-effort output reserve as the total canonical-response ceiling. The adapter also retains encrypted reasoning in that response. | Q-004; `core/budget.py`; `model_reviewer.py`; `brokered_openai.py` | Separate visible-answer and canonical-envelope limits without changing token/spend authority. |
| 2026-09-20 | decision | Initially use the existing 4,000-byte output reserve for visible JSON text and add a separately bounded response-envelope limit, capped by the model registry. | Python guide and threat model | Test that assumption against the exact retained response shapes before finalizing it. |
| 2026-09-20 | observation | Exact offline inspection disproved the 4,000-byte answer assumption: the retained visible JSON bodies were 4,243 and 2,680 bytes, while their canonical envelopes were 8,617 and 8,221 bytes. | Private final-campaign artifacts; no provider or credential access | Use an explicit 8,000-byte visible-answer cap and a separate 64,000-byte canonical envelope. Preserve the 4,096-token and spend ceilings. |
| 2026-09-20 | implementation | Added independently sealed `max_text_output_bytes` and `response_envelope_bytes` contracts. The reviewer and broker enforce UTF-8 text bytes and whole canonical bytes independently, and the launch configuration serializes both limits explicitly. | Source diff and request-hash tests | Exercise exact boundaries, opaque-reasoning acceptance, launch projection, and old-profile compatibility. |
| 2026-09-20 | error | The first focused test command found that an over-limit synthetic answer violated the independent 8,000-character per-block contract before reaching the aggregate-answer assertion. Two suites also require standard discovery so sibling fixtures are importable. | Focused unittest output; `TextBlock` contract; existing test imports | Split the synthetic answer across valid blocks and rerun through test discovery; do not change product limits. |
| 2026-09-20 | verification | Exact offline replay of both retained response shapes under the corrected profile parsed and passed citation validation at 8,617/4,243 and 8,221/2,680 canonical/text bytes. Historical failed receipts were not changed or reclassified. | Private read-only replay output | Run repository regression and production gates. |
| 2026-09-20 | verification | Review/provider/protocol focused and broad regression suites passed: 422 tests total before the final explicit-serialization assertion; the post-change focused protocol and launch suites are rerun separately. | Local unittest output | Complete `make check`, container gate, and adversarial review. |
| 2026-09-20 | error | The first container gate correctly rejected the isolation smoke's manually constructed broker request because that fixture had not declared the new required text cap. Build, CLI and the earlier smoke passed before this fixture failure. | `make container`; `tools/smoke_isolation.py` | Bind the fixture's existing 4,000-byte intended answer limit explicitly and rerun the complete container gate. |
| 2026-09-20 | verification | Unrestricted `make check` passed Ruff, Pyright, 2,451 source tests with four skips and 89% coverage, export verification, package builds and 1,842 installed-wheel tests. The complete corrected `make container` rerun then passed every isolation/review smoke. | Final gate output | Close the adversarial review with no open blocker. |

## Handoff

- Current state: correction implemented; exact replay, full project gate, container
  gate and adversarial review pass. Historical qualification remains terminal.
- Next smallest safe action: owner review and commit if desired. Do not infer any
  replacement campaign or provider authority from this code correction.
- Blocker and required authority/input: no blocker; no live/provider authority is
  required or granted.
- Checks already run: exact private-shape offline replay; focused budget, reviewer,
  broker and launch tests; 422-test broad regression set; full `make check`; complete
  `make container`; no provider call.

## Close and promote

- Outcome and verification: Q-004's code defect is corrected with independently
  request-bound text/envelope limits; exact replay and all required gates pass.
- Durable fact promoted to `PROJECT_MEMORY.md`: corrected limits and the immutable
  terminal qualification result
- Decision promoted to ADR/documentation: `docs/MODEL_REVIEWER.md`, threat model,
  incident review and adversarial review; no new ADR was required
- Regression test, issue, or improvement-plan link: focused protocol, reviewer,
  broker, launch-preview and isolation-smoke coverage
- Temporary artifacts removed: gate-owned temporary environments were removed;
  ignored package outputs and the local Docker image are normal gate artifacts
