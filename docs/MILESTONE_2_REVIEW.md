# Offline agent-loop milestone adversarial review

Date: 2026-09-05. Scope: canonical protocol, registry, byte budgets, fixture tool,
request-bound recorded adapter, journal and replay. Reviewer: implementing
assistant, self-review; no independent model or live-provider review was performed.

Disposition: suitable for deterministic offline development. It is not evidence of
vendor compatibility, token/cost accuracy, host containment or review quality.

## Findings and corrections

| Impact | Finding | Correction / evidence |
|---|---|---|
| High | Per-block validation allowed assistant tool results and user tool calls | Role-specific block validation and negative tests |
| High | A syntactically valid replay could splice orphaned, missing or reused call IDs | Whole-history alternation and exact pending-result validation |
| High | Slow providers/tools and endless tool selection lacked independent ceilings | Provider/tool deadlines plus iteration and tool-call limits |
| High | Raw adapter exceptions could cross the CLI boundary | Hash/status failure journal and generic `AgentFailure` wrapping |
| Medium | Tool failure attempts were absent from the journal | `tool.failed` events for timeout, exception, mismatch and oversize output |
| Medium | Existing history call IDs were not included in reuse detection | Seed the used-ID set from validated initial turns |
| Medium | Nested canonical JSON depended on Pydantic's mapping order | Explicit recursively sorted, compact JSON serialization |
| Medium | Schema enums could contradict declared scalar types or grow unbounded | Type-aware enum validation and schema collection/text limits |
| Medium | A journal write could spin if the OS reported zero progress | Treat zero-byte writes as an I/O failure; fsync every event |
| Low | A copied manifest could identify a different run directory | Bind stored run ID to its directory name during load |

## Verification

- Ruff lint/format and strict Pyright: passed.
- Unit/integration/architecture suite: 48 tests passed; 94% combined statement and
  branch coverage (85% enforced floor).
- Recorded agent demo performs two provider turns and one fixture lookup; replay
  compares the entire result, every journal event and cassette exhaustion.
- Wheel/container smoke tests are extended to exercise both review and agent replay.

## Remaining work

No live provider is present. Byte limits are not token or cost limits. The journal
records hashes rather than a resumable full transcript. Async deadlines cannot
preempt blocking adapter code. The fixture dispatcher provides no evidence for a
safe filesystem, process, network, Git or test-execution boundary. Model capability
claims remain fixture assertions until a conformance suite verifies a live adapter.

Next review trigger: the first live provider or any machine/network capability.
