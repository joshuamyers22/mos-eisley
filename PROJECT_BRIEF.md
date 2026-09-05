# Project Brief

- Problem and affected users: developers need independent, evidence-backed review
  of code changes across competing model providers without sharing author history.
- Implemented milestones: explicit brief -> recorded critics -> dedupe -> recorded
  judge -> policy verdict, plus a provider-neutral multi-turn agent loop using an
  inert fixture tool. Both paths produce private, content-verified offline replays.
- Provider preview: OpenAI Responses API adapter and opt-in single-prompt command;
  capabilities are documented but not credential-conformance verified.
- Success criteria: documented CLI works from the built wheel; missing quorum,
  malformed evidence and malformed tool histories fail closed; identical recordings
  reproduce identical results; strict typing, tests, >=85% branch-inclusive coverage,
  packaging and CI are green.
- Non-goals for this phase: live adversarial review, machine tools, sandboxing, test
  execution, repository config, GitHub writes, author agents, TUI and model pricing.
- Runtime: Python 3.12+, uv, macOS/Linux; non-root container for operational use.
- Inputs: user-selected JSON files, bounded before parsing. At most eight critics,
  fifty findings per critic; request budgets and 10-second call deadlines enforced.
- Data: recorded workflows stay local. `openai-run` sends only named prompt and
  instruction files after acknowledgement and never stores its environment key.
  Run files mode 0600 and new run directories mode 0700. Manual retention.
- Recovery: run artifacts are authoritative. Missing/invalid manifests reject
  replay; an unavailable SQLite index does not discard completed evidence.
- Failure scenarios: fabricated evidence, unknown judge IDs, missing critics,
  oversized files, symlinks/FIFOs, corrupted runs, malformed tool pairing, reused
  call IDs, adapter/tool timeouts, iteration/tool exhaustion and cancellation.
- Owner: Josh Myers. Production rollout and quality calibration remain future work.
- Architecture choices: see `docs/adr/0001-offline-foundation.md`,
  `docs/adr/0002-canonical-agent-protocol.md` and
  `docs/adr/0003-openai-first-provider.md`.
