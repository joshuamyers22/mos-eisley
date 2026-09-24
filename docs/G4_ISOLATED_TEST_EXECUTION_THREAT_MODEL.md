# Threat Model: G4 isolated reviewer-test execution and counts

## Scope and ownership

- System/version: Mos Eisley at
  `331874d0da17e43cd5115f7d3ff65f62f1d2afbc`.
- Owner/reviewer: Joshua Myers; implementation by Codex.
- Date and review trigger: 2026-09-24; new execution request, worker, count receipt,
  control validator or containment change.
- In scope: bounded local input assembly, immutable-image offline execution,
  direct-import adapter materialization, exact unittest observations and paired known
  controls. Out of scope: trusted Git/E2 provenance, dependency installation,
  reviewer independence, correction dispatch and acceptance.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Frozen reviewer package | private executable input | exact canonical bytes and collection contract | project owner |
| Bound implementation material | private executable input | exact declared source/resource bytes | project owner |
| Immutable container image | executable trust root | exact local SHA-256 image and fixed confinement | project owner |
| Execution/count receipt | private evidence | canonical, immutable, exact input/outcome binding | project owner |
| Known-control validation | qualification evidence | same package/adapter/image and correct opposite outcomes | project owner |

- Actors and capabilities: explicit CLI operator, hostile reviewer package, hostile
  implementation, compromised dependency/image, Docker daemon, and same-UID host
  process outside the boundary.
- Entry points and trust boundaries: canonical request/binding/package, implementation
  root, Docker executable/image and new receipt path.
- Data flows and external dependencies: host validates exact local bytes, sends one
  bounded canonical job over stdin to a no-mount container, receives one bounded
  observation and writes a private receipt. There is no network/provider edge.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Fake adapter or result interception | executable adapter supplied | false pass | worker generates only direct import aliases from bound schema; no adapter input | adapter-source and hostile-job tests | dynamic Python can still mutate runtime state |
| Stale/substituted package or tree | input changes around launch | wrong code tested | canonical binding/package validation, exact material hashes, pre/post replay and job identity | drift/race tests | transient same-UID change-and-restore remains possible |
| Empty/skip/xfail collection | hostile discovery behavior | vacuous pass | exact frozen collected/executed/skipped counts and ordered-ID digests | count mismatch tests | test IDs are unittest-defined strings, not semantic proofs |
| Known-bad fails for wrong reason | import/crash treated as detection | false sensitivity claim | bad control requires assertion failure, zero errors and exact counts | positive/negative control tests | fixture representativeness remains reviewable |
| Test escapes to host/network/secrets | hostile Python | compromise/exfiltration | immutable image, no mounts, network none, non-root, cap drop, no-new-privileges, read-only root, private tmpfs and minimized inherited environment | fixed-command regression | Docker daemon/image and kernel remain trusted |
| Fork/output/resource bomb | hostile Python | denial of service | PID/memory/CPU/nofile/tmpfs limits, bounded stdin/stdout/stderr and deadline watchdog cleanup | timeout/output/cleanup tests | host Docker overhead remains external |
| Worker imports installed target instead of materialized tree | target name overlaps worker package | wrong code tested | validated controller launches a clean isolated child interpreter with materialized roots first | same-name regression | dependencies still come from the immutable image |
| Receipt mistaken for correction/acceptance | downstream misuse | unauthorized changes | all downstream authority fields false; known-control record is evidence only | contract/CLI tests | later components must re-enforce gates |

## Decisions

- Accepted risks with owner and expiry: Docker/image/kernel trust, dynamic Python
  semantics, transient same-UID restore races and dependency/image correspondence are
  owned by Joshua Myers until trusted VCS/E2 and final G4 review. Inputs that exceed
  the existing 16 MB isolated wire bound are rejected rather than streamed or mounted.
- Required tests and monitoring: known-good/known-bad real worker runs; exact-count,
  tamper, import-error, timeout/output, drift, canonical-record, Docker flag and cleanup
  cases; static/full/build/wheel gates.
- Incident and recovery dependencies: discard the receipt and container lifecycle,
  correct the immutable inputs or runner, then create a fresh request and receipt.
  Never edit a receipt or weaken the frozen collection contract.
