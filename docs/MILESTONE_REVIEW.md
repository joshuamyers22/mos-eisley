# Initial milestone adversarial review

Date: 2026-09-05. Scope: local offline foundation generated from template commit
`3d467040ba760efe9795f67f07d5a2ccf364282b`. Reviewer: implementing assistant,
self-review; no independent model review was performed. Local branch: `main`;
initial work is uncommitted and unpublished.

Disposition: suitable for offline development. Not a production live-review tool.
The strongest property is the absence of executable/network authority in the
recorded adapter. The largest outstanding product risk is unmeasured model quality.

Architecture: CLI composition -> review use case -> immutable contracts and owned
reviewer protocol. Recorded provider and filesystem adapters depend on those
contracts. Inner-layer import restrictions have an executable architecture test.

## Findings and corrections

| Impact | Finding | Correction / evidence |
|---|---|---|
| High | Missing critic or judge could be mistaken for no findings | Quorum and distinct infrastructure error; negative tests |
| High | Unknown/duplicate judge IDs can corrupt required changes | Validate membership and uniqueness before adjudication |
| High | Restored manifest could request arbitrary paths | Exact artifact set validated before reads; traversal regression |
| Medium | Valid recorded input can expand past replay's file limit | Bound every saved payload before creating output directories |
| Medium | Digest verification alone does not verify derived verdict | Recompute and compare the entire result; matching-hash regression |
| Medium | File existence checks permit symlinks/FIFOs | Nofollow/nonblocking open plus fstat and bounded read |
| Medium | Index failure could lose access to completed evidence | Preserve artifacts and report index degradation |
| Low | Build command accepted an unsupported frozen flag | Build with the locked Hatchling backend through frozen uv run |

## Verification

- Ruff lint/format and strict Pyright: passed.
- Unit/integration/architecture suite: 26 tests passed; 98% combined statement and
  branch coverage (85% enforced floor).
- Runtime export comparison: passed.
- Wheel and sdist build: passed; wheel installed into a fresh environment and
  synthetic review/replay exercised outside the source checkout.
- Dependency audit: five runtime dependencies, no known vulnerabilities or adverse
  project statuses reported by `make audit`.
- Container: pinned base, UID 10001, read-only root, network disabled; recorded demo
  and replay passed with capabilities dropped and no-new-privileges enabled.
- GitHub CI/release workflows: configured, not run remotely; no remote exists yet.

## Remaining work

Live-provider conformance, token/cost accounting, actual machine isolation, evidence
execution, statistical quality calibration and authenticated publication remain
unimplemented. File hashes do not authenticate the author. Parent directories and
same-UID processes are trusted. Completed-run event summaries are not per-request
crash journals. Citation presence is not proof of correctness. These limits are
documented in the project brief and threat model and constrain the next milestone.

Next review trigger: adding a live provider or any new machine/network capability.
