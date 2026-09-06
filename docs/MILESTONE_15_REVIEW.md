# Routing-study pre-registration review

Scope: offline validation and sealing of a label-free feature partition and routing
study design. No observations, grades, scores, provider calls, route fitting,
holdout access, configuration mutation, activation, or publishing is included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| Analyst redraws easy/hard groups after seeing outcomes | Numeric boundaries and exact categorical partition fields are content-addressed in the protocol before scoring | A local digest does not prove publication time; use an external append-only attestation before collecting outcomes |
| Manifest quietly embeds outcome labels | Strict feature schema permits only pre-dispatch observables; expected findings and results have no fields | Operator-authored metadata or case IDs may still correlate with labels and require review |
| Feature row is joined to a different prompt | Require exact dataset coverage, case ID, brief digest, recomputed canonical brief bytes, and matching deterministic risk tags | Changed-file, changed-line, language, role, output, and tool values remain operator assertions |
| Policy selects a route below the role floor | Each role has a reviewed allowlist; its fallback must be in that list and every listed route must exist in the pinned sweep | The code cannot infer model capability ordering or judge whether the allowlist is prudent |
| Sparse profiles are pooled after inspection | Require every pre-registered profile to contain clean and defective cases in both splits | Passing the structural check does not provide enough independent groups; the scorer must still enforce power and simultaneous bounds |
| A receipt is edited or detached from its sources | Bind protocol, dataset, full plan, manifest, and derived profile IDs; provide full deterministic reverification | Consumers must retain and independently supply all sources |
| “Sealed” is mistaken for approved production policy | Both protocol and receipt contain literal `activation_authorized=false`; the CLI has no results input or runtime/config capability | Calibration fitting, one-time holdout governance, drift detection, promotion signatures, and activation remain future gates |

The next change should extend the statistical comparison family across all sealed
profiles and routes, score calibration evidence only from reverified dual lineage,
and emit a frozen candidate policy that remains non-activating. Holdout data must
not be an input to that fitter.
