# Project Brief

- Problem and affected users: developers need independent, evidence-backed review
  of code changes across competing model providers without sharing author history.
- First milestone: explicit brief -> two recorded critics -> dedupe -> recorded
  judge -> policy verdict -> private artifacts -> verified offline replay.
- Success criteria: documented CLI works from the built wheel; missing quorum and
  malformed evidence fail closed; identical recordings reproduce identical results;
  strict typing, tests, >=85% branch-inclusive coverage, packaging and CI are green.
- Non-goals for this milestone: live model calls, machine tools, sandboxing, test
  execution, repository config, GitHub writes, author agents, TUI and model pricing.
- Runtime: Python 3.12+, uv, macOS/Linux; non-root container for operational use.
- Inputs: user-selected JSON files, bounded before parsing. At most eight critics,
  fifty findings per critic; request budgets and 10-second call deadlines enforced.
- Data: private source/recordings, no network transfer. Run files mode 0600 and new
  run directories mode 0700. Manual retention; SQLite holds only lookup metadata.
- Recovery: run artifacts are authoritative. Missing/invalid manifests reject
  replay; an unavailable SQLite index does not discard completed evidence.
- Failure scenarios: fabricated evidence, unknown judge IDs, missing critics,
  oversized files, symlinks/FIFOs, corrupted runs, timeouts and cancellation.
- Owner: Josh Myers. Production rollout and quality calibration remain future work.
- Architecture choices: see `docs/adr/0001-offline-foundation.md`.
