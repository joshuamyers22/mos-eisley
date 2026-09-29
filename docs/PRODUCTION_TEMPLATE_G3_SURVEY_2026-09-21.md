# Production-template survey for G3 utility-study planning

## Source and scope

- Repository: `https://github.com/joshuamyers22/production-project-template`
- Reviewed local `main`: `237330dc7f6424dafcb172aa7ca776e755c71610`
- Commit date: 2026-09-21
- Prior Mos Eisley pin: `8879be48f3b760e65f6bed32f8740314fe92910d`
- Survey date: 2026-09-21
- Scope: repository/agent baseline, Python and bounded-verification guidance,
  work-note/verification templates, statistical-analysis plan and quantitative
  statistical-learning point of view.

The current local template checkout is clean and matches its `origin/main`. No
template code or dependency was installed into Mos Eisley.

## Relevant source identities

| Source | SHA-256 |
|---|---|
| `AGENTS.md` | `902132acc9c37998a0e6f77518592280a7e695eab3d66b056485b7cf83fcf801` |
| `standards/PRODUCTION_REPOSITORY_STANDARD.md` | `9549d30b491c466aacb8152242f1caf1e7a68761bd6a74387bf56d100d1809c5` |
| `docs/PYTHON_ENGINEERING_GUIDE.md` | `9b6ae36bc08a34f0100dce2d4cf2947f110fc5114773070505d12539015d6f9e` |
| `docs/AGENTIC_VERIFICATION_GUIDE.md` | `f0ea5eba1e0a90fb8263252d3d3779a3b70645e99f2e07d2e6095a5d04932ca2` |
| `templates/AGENTIC_VERIFICATION_LOOP.md` | `426a11484eb026b45e2c51e6cb69a16f58768627dad7a9b5502a7de0ee5fc17f` |
| `templates/WORK_NOTE.md` | `ddaa662dde003c1feeb19d1df4a8abe47db2ea394054ad439b76f355fb49f332` |
| `templates/STATISTICAL_ANALYSIS_PLAN.md` | `f816984c5e7fc41a735feef5ca2e05cdc3fa987a5aeecb66f0ddb9616d8b6142` |
| `docs/QUANT_STATISTICAL_LEARNING_POINT_OF_VIEW.md` | `0af1bda6d7bf93fef1c33c683bec510d06ba7e2b3f9bacbe29b515f9ab0f0399` |

## Findings and selection

The relevant guidance files are byte-unchanged from Mos Eisley's 2026-09-19 pin.
Intervening upstream changes concern dependency updates, deterministic C++ formatting
and qualified refactoring/locality guidance; they do not alter this study's fixed-
matrix inference, ownership, holdout or spending constraints.

For G3, select:

- `templates/STATISTICAL_ANALYSIS_PLAN.md` to state the decision, estimand, sample,
  baselines/ablations, protected assessment boundary, uncertainty, cost and approval;
- `docs/PYTHON_ENGINEERING_GUIDE.md` for strict immutable contracts, pure calculation,
  deterministic serialization, bounded inputs and negative tests;
- `docs/AGENTIC_VERIFICATION_GUIDE.md` and its template for evidence-changing passes;
- `templates/WORK_NOTE.md` because G3 is a multi-session empirical milestone.

The quantitative point of view is useful only at its general boundaries: begin with
the decision, earn complexity against a baseline, separate selection from final
assessment and preserve disappointing evidence. Mos Eisley's approved plan and
`docs/STATISTICAL_DESIGN.md` remain authoritative for the actual estimand and fixed-
matrix method. The template does not authorize data access, provider spend, holdout
inspection, execution, promotion or routing.
