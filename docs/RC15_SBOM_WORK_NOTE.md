# rc.15 SBOM generation and completeness

- Status: active implementation; new candidate only, no publication approval.
- Owner: Joshua Myers; operator Codex. Started 2026-11-04 UTC.
- Review by: 2026-11-11 or candidate change.
- Baseline: main `1b3dd26bf59eb604ae7245e1223518cddbed3e7c`, runtime source
  from immutable rc.14 `ec3211e23c4a3e2b20837114e707bc8ebcbe625a`.
- Requirement: [readiness assessment R14-01](https://github.com/joshuamyers22/mos-eisley/pull/362).

## Objective, invariants and evidence

Replace the empty directory scan with a deterministic release SBOM built from
actual packaged artifacts and their runtime metadata. Independently recompute
coverage before any draft preflight/publication, rejecting empty or missing
critical dependency/interpreter/native-file inventories, wrong source/version,
tampered hashes and incomplete platform sets. Freeze the fix as rc.15 without
changing rc.14, any historical receipt, native grant or model profile.

Selected guidance: repository Python engineering, bounded verification and
adversarial review guides; work-note, threat-model and verification-loop templates;
production release checklist. Risk: material release/supply-chain boundary.
Operator tests are not accountable independent release approval.

The old SBOM is 402 bytes with no top-level components or dependency graph.
Its scan ran before native artifacts arrived. Actual rc.14 archives also contain
metadata for only part of the locked runtime set; moving the scan alone cannot
establish software coverage. No vulnerability or license violation is inferred.

## Design and stopping rules

Build a standards-compatible CycloneDX inventory from bounded archive reads,
actual distribution metadata and hashes, a source-bound runtime receipt and the
hash-pinned runtime export. Preserve unknown native versions/licenses honestly;
never invent identities or count a nonempty list as sufficient coverage. No
archive extraction, metadata execution, network cataloging or key access belongs
in validation. Keep publication checks usable without runtime dependencies.

Native builders must include dependency metadata and record the actual frozen
CPython version through credential-free diagnostics. Runtime license evidence is
copied from the same managed interpreter. The SBOM covers software payloads;
qualification reports and the SBOM/checksum itself are excluded to avoid cycles.
Unknown or unsupported marker/metadata forms fail closed rather than silently
omitting a dependency. Full license/legal clearance remains separate from faithful
inventory of declarations and included license files.

Threats: incomplete/padded inventories, platform or source substitution, forged
runtime receipts, archive links/traversal/duplicates/bombs, unbounded metadata,
unsafe license paths, stale package versions and mutable uploads. Tie the expected
inventory to the frozen dependency export and actual file bytes; compare complete
components and relationships before GitHub requests can publish anything.

Bounds: two coherent boundary passes plus targeted correction; one combined
`make check` under four-hour wall/monotonic ceilings; one local native build and
normal required CI for the frozen candidate. Six-hour engineering/review window,
zero model calls, no release-key inspection or release publication. Stop on
identity, cleanup or required-check failure and preserve the first failure. Do
not reinterpret historical rc.14 qualification under the new publisher contract.

## Verification and handoff

Focused boundary checks pass: 14 SBOM/archive/diagnostic tests, 18 publication
checks and 42 distribution checks; strict source and release-tool typing and
format/lint pass. Official CycloneDX 1.6 schema validation is offline; the
publisher remains stdlib-only. The all-target CI assembly inventories real native
payloads using explicitly unsigned auxiliary fixtures; protected preparation
recomputes the BOM over actual publication files. Archive ceilings include
512 MiB input, 128 MiB member, 2 GiB total expansion, 20,000 entries, 512 KiB
individual retained metadata and 16 MiB retained metadata per archive.

Pending actual local native inventory, combined gate and final candidate freeze. Preserve the current dependency set; regenerate the lock only
for the project version bump. Add actual rc.14 predecessor admission for the new
candidate. Publication and separately authorized affected signed qualification
remain later steps; no native-inference campaign is granted by this work note.
