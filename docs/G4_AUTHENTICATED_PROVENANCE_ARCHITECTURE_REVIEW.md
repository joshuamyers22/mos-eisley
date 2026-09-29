# Adversarial architecture review: G4 authenticated provenance

## Review metadata

- Repository/branch: mos-eisley-memory-selection / feat/production-template-guidance
- Starting commit: `2f02080d`
- Reviewer: Codex; accountable owner Joshua Myers
- Date: 2026-09-24
- Scope: new custody policy/artifacts, read-only Git broker, final record, CLI and tests
- Exclusions: private-key custody, live children/providers, Git writes and correction
- Blocking threshold: any signature substitution, executable Git configuration,
  wrong-tree acceptance, weak child lineage or downstream authority

## Executive verdict

- Overall grade: pass for the offline authenticated-provenance slice.
- Release recommendation: retain as offline G4 infrastructure; do not authorize
  candidate/correction dispatch or final acceptance.
- Highest risk: a signed but wrong revision or a metadata-only child being presented
  as exact implementation provenance.

## Verification evidence

| Check | Command | Result |
|---|---|---|
| Static/focused | focused Ruff, Pyright and combined G4 unittest modules | pass; zero static findings and 33/33 G4 tests |
| Process compatibility | unittest discovery for `test_isolation.py` | pass, 7/7 |
| Git/signature attacks | `tests.test_reviewer_provenance` | pass, 8/8 disposable-repository cases |
| Full source | `make check`; affected loopback rerun | reconciled pass; 2,464 observed, 31 expected sandbox errors, same 48 pass unrestricted |
| Build/package | `make verify-export build`; wheel inventory; `make smoke` | pass; modules present and 1,787/1,787 installed tests |

## Architecture map

- Domain: immutable policies, signed phase artifacts, Git and final records.
- Application: verify custody; reconstruct Git lineage; assemble/replay provenance.
- Infrastructure: absolute read-only Git executable through bounded process plumbing.
- Delivery: explicit G4 record/assemble/verify CLI commands with private no-overwrite
  output.

## Findings

- Closed, high: the first assignment draft asserted test protection without binding
  an exact creator-test path inventory. The signed assignment now requires a sorted,
  nonempty inventory marked complete, rejects overlap with owned paths, and Git
  replay mechanically limits actual changes to owned paths.
- Closed, high: the first Git pass checked `HEAD` before reconstruction only. It now
  checks the same exact commit after all mutable binding and worktree reads; remaining
  tree lookups use exact immutable object IDs.
- Accepted residual: signatures prove enrolled-key control, not physical identity,
  secure custody, honest judgment or external time. Test-inventory completeness and
  meaningful-subtask status are accountable signed claims. Git, OS and same-UID
  state remain trusted; candidate/correction/final-review authority is absent.

## Clean Code and architecture checks

- [x] Invalid role, mode, timestamp, path and lineage states fail at contract edges.
- [x] Signature domains and canonical encodings are explicit and versioned.
- [x] Domain verification is independent of CLI and process infrastructure.
- [x] Git execution is centralized, fixed-argv, shell-free and read-only.
- [x] Production CLI accepts no private key and writes private no-overwrite records.
- [x] Outputs retain literal non-authority rather than implying permission.
- [x] Real disposable Git fixtures cover clean success and hostile repository state.

## Follow-up review

- Review date: 2026-09-24 after source, build and installed-wheel verification.
- Findings closed/remaining: two high findings closed; only documented external trust
  and later G4 gates remain.
- Next review trigger: signature/policy/Git/path/binding/final-record schema change.
