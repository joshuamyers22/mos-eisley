# Dual-lineage scoring review

Scope: offline statistical scoring of a fully reverified authenticated grading
chain. No provider calls, route selection, configuration mutation, policy
activation or publishing is included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| Edited observations are scored under an authentic-looking hash | Reconstruct every private source, reverify dual grading, and compare the exact derived observation artifact before scoring | Source retention and independent policy distribution are operator duties |
| Wrong split or partial matrix improves metrics | Require exact equality with the requested split's full case × route × repetition keys | Correct split designation in the pre-registered dataset remains trusted after hash verification |
| Authenticated and rehearsal paths use different formulas | Share one scoring implementation after source-specific provenance validation | Changes to statistical design still require independent review and schema migration |
| Report drops inconvenient lineage | Bind dataset, plan, batch, map, raw result, grading packet, both policies, resolution and observation digests | Hashes do not provide external timestamping or transparency |
| Edited stored scores are trusted | Provide deterministic full-chain report recomputation and exact equality verification | Consumers must actually invoke verification and retain all sources |
| Passing route is activated automatically | Literal `promotion_ready=false`; CLI has no provider, registry, config or publisher authority | Future policy derivation and activation need separate reviewed capabilities |

Route-level `eligible` remains a measurement against one registered gate, not a
deployment decision. The next quality gate is a pre-registered protocol for
deriving an interpretable difficulty policy on calibration data, freezing it, and
evaluating it once on protected holdout data without granting activation authority.
