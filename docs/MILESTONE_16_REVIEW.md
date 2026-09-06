# Profile calibration scoring review

Scope: offline profile-aware statistical scoring of authenticated calibration
outcomes. No holdout outcomes, policy selection, provider calls, configuration
mutation, activation, or publishing is included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| Analyst changes bins after seeing performance | Reverify the content-addressed sealed protocol and independently supplied feature manifest before scoring | External publication time and analyst conduct are not attested locally |
| Holdout results enter the fitter | Hard-code calibration and require exact equality with its full observation matrix; expose no split argument | The complete labeled dataset is needed for digest validation, and external holdout access remains an operational control |
| Profile comparisons reuse narrower route-only bounds | Expand the family across profiles × routes × three metrics × both splits and record/validate the dimensions on every profile | Bonferroni is conservative and the method still needs independent statistical review |
| Sparse profiles or repeated cases manufacture evidence | Sealed study requires both case types in both splits; group-aware scoring averages repetitions before independent groups and retains the minimum-group gate | Independence groups, semantic duplicates, and representativeness remain operator claims |
| Convenient routes outside the role floor bias scoring | Score every planned route for correct family accounting, but make no selection in this artifact | The later freezer must apply the sealed allowlist before selecting |
| Edited scores retain plausible lineage hashes | Deterministically rebuild from all private execution and authenticated grading sources and require exact report equality | All sources must be retained and independently supplied by consumers |
| Passing calibration is treated as deployment approval | Distinct strict report schema, no selected route, and literal promotion/activation denial | Freezing, one-time holdout evaluation, drift controls, signed promotion, and runtime activation remain separate gates |

The next change should freeze a deterministic candidate policy using only this
calibration report and the reverified sources. Missing cost evidence must make the
profile uncalibrated, and holdout outcomes must not be accepted by the freezer.
