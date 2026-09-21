# Work Note: G3 context policy and label eligibility

- Status: closed for the offline sealing boundary; empirical inputs remain open
- Owner: Josh Myers
- Started/updated (UTC): 2026-09-21
- Review by: real G3 label intake or policy revision
- Related: roadmap G3; plan §§6.7.6, 18 and 26

## Objective and invariants

Freeze the exact baseline, full context candidate and component ablations, then create
a content-addressed eligibility inventory from independently signed label metadata.
Never read held-out sessions, treat fixtures as evidence, impute missing labels, or
grant execution/promotion authority.

## Context and decisions

- Selected `docs/PYTHON_ENGINEERING_GUIDE.md`, the bounded-verification guide/template
  and the threat-model template.
- Existing result adjudication signs judgments about model output; it is not a source
  of pre-study ground truth. A separate signature domain prevents semantic reuse.
- The inventory accepts opaque case digests and aggregate label metadata only.
- Exactly one ablation per candidate component is retained even when unavailable.
- Repository inspection found no real signed G3 label catalog or trust policy. Current
  empirical eligible count is therefore zero; synthetic tests are excluded from claims.

## Evidence and handoff

- Focused Ruff and Pyright pass.
- Fifteen focused context-study and feasibility tests pass; 26 related evaluation
  regressions pass; affected branch coverage is 89%; full Pyright reports zero errors.
- A provenance review found that the first seal boundary trusted a serialized inventory;
  it now requires the catalog/trust policy again and rebuilds eligibility before sealing.
- A privacy review replaced readable case and independence-group identifiers with opaque
  SHA-256 references; the digest-to-session map remains outside this boundary.
- Full repository gate passes: Ruff and format checks, Pyright with zero errors, 2,497
  source tests with 4 skips and 89% coverage, export verification, wheel/sdist build,
  and 1,855 tests against the installed wheel.
- After the final opaque-identifier edit, focused Ruff/format and all 15 affected tests
  pass at 89% affected branch coverage; the installed wheel contains that final edit.
- External inputs after implementation: real independently controlled grader keys and
  claims, reviewed arm/source hashes, resource plan and statistical approval.
