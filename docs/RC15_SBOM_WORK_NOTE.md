# rc.15 SBOM generation and completeness

- Status: closed; source fix, affected qualification and verified rc.15 publication complete.
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

Focused boundary checks pass: 18 SBOM/archive/diagnostic tests, 18 publication
checks and 42 distribution checks; strict source and release-tool typing and
format/lint pass. Official CycloneDX 1.6 schema validation is offline; the
publisher remains stdlib-only. The all-target CI assembly inventories real native
payloads using explicitly unsigned auxiliary fixtures; protected preparation
recomputes the BOM over actual publication files. Archive ceilings include
512 MiB input, 128 MiB member, 2 GiB total expansion, 20,000 entries, 8 MiB
central directory, 512 KiB
individual retained metadata and 16 MiB retained metadata per archive.

Actual local macOS arm64 builds at `45c769b5d810ba6beb647967e160dfcb90a8ff34`
pass both frozen-runtime probes (CPython 3.12.14). Application: 904 files, 44
observed metadata records, all 42 target-selected runtime dependencies. Bootstrap:
163 files, four metadata records and all three bootstrap dependencies. Every
declared native license file is present. These are local engineering builds,
not signed qualification. Build log SHA-256:
`0a7a0803d9fe6dff0a1fb27237ac5d13fc4dca9064a8a4114d9bd682ceb43f0a`;
inventory receipt: `b7d6e49c843466805c0bafaf05624529adc06e6c17573888b11b797f4bb03408`.

The adversarial pass identified eager tar extended-header and ZIP directory
allocation before member checks. The corrected readers bound those operations
before stdlib parsing. Refusal controls and actual local sdist/native tar parsing
pass. This tooling-only correction was prepared in a separate checkout while the
combined gate retained immutable inputs at `45c769b`; affected tests/types pass
again, and the final PR head must pass hosted source and all-target coverage.

The first secret scan flagged a public SPDX license-name enumeration in the
unmodified official schema. The exception is restricted to introducing commit
`45c769b`, fixture path, generic-api-key rule and line 1; no broader rule or path
is disabled. No credential value is present.

The first hosted assembly failed closed because Hatch preserves the raw
`0.1.0-rc.15` package metadata version while uv normalizes it to `0.1.0rc15`.
Source/export/interpreter/platform records all matched. Normalize the application's
supported raw/PEP 440 prerelease forms before comparing metadata identities;
retain exact tag and source bindings. A regression covers both forms. Recomputing
the retained real four-platform software set (with unsigned auxiliary fixtures
and locally rebuilt wheel/sdist metadata) yields 6,484 components. The original
failure remains in [run 41928827372](https://github.com/joshuamyers22/mos-eisley/actions/runs/41928827372).

A typed-JSON refusal control also reproduced Python mapping equality treating
boolean `true` as integer BOM version `1`. Admission now compares typed canonical
JSON and rejects non-finite scalars; it cannot accept that standards-invalid
substitution. The regression fails before the correction and passes afterward.
The corrected retained inventory passes official schema validation and independent
bootstrap-reader size/hash agreement on every embedded member (receipt SHA-256
`ae6fc1285956087c7b42f9de527e5ab8fafa71cd0c05f190e3a211d01bcab2ae`).

Combined gate and final-head hosted checks are pending; this is the pre-CI freeze
record. Subsequent exact-head results are recorded in PR #363's body/check rollup. PR #363 is the candidate
review; no release tag has been created. Preserve the current dependency set; regenerate the lock only
for the project version bump. Add actual rc.14 predecessor admission for the new
candidate. Publication and separately authorized affected signed qualification
remain later steps; no native-inference campaign is granted by this work note.

## Qualification closeout

The owner requested review/merge and protected signing/affected qualification.
PR #363 merged normally; frozen source `21fc2b0` is preserved in main history.
Protected run 41948231550, attempt 1, passed all four signed jobs. The actual
review admits 58 reports and 76 assets, with a nonempty 6,485-component SBOM and
successful read-only preflight. The pre-CI statements above remain the original
freeze record; see the [completed evidence review](RC15_QUALIFICATION_REVIEW.md)
and [qualification work note](RC15_QUALIFICATION_WORK_NOTE.md). Publication stays
at its protected owner gate. Original failures and rc.14 receipts are unchanged.

## Public replacement

The owner accepted publication; immutable rc.15 now contains the verified
6,485-component SBOM. All 76 public assets and attestation match the qualified
candidate, and a fresh public macOS arm64 installation passes. See the
[publication work note](RC15_PUBLICATION_WORK_NOTE.md). rc.14's historical empty
SBOM and all original failures remain unchanged.
