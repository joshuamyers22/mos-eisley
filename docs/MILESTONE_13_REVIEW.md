# Dual-lineage observation compilation review

Scope: offline joining of a fully authenticated dual grade to the private
evaluation mapping. No provider execution, scoring, policy promotion or publishing
is included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| Correct grades are joined to altered routes, cases or raw results | Reconstruct the grading packet through the complete dataset, plan, batch/map and raw-result chain; require exact packet equality | All explicitly supplied controller inputs remain trusted until verified |
| A stored resolved judgment is trusted without checking its signatures | Rebuild the dual-grade artifact from both embedded receipts, independent policies and signed resolution before joining | Enrolled humans and policy administration can still be wrong |
| Compiler silently substitutes one grader's labels | Use only the reverified `resolved_judgments`; preserve the complete dual-grade artifact digest | The linked source artifact must be retained separately |
| Rehearsal and authenticated compilers calculate metrics differently | Share one pure judgment-to-observation join implementation after each path completes its own validation | Future observation schema changes require both paths to be reviewed |
| Derived observations are edited after compilation | Content-address the complete output and provide full-chain deterministic reverification | Hashes alone do not provide external notarization |
| Authenticated observations enter the legacy scorer by structural similarity | Use a distinct strict schema with no legacy adjudication digest and literal `promotion_eligible=false`; CLI parsing rejects it as `ObservationSet` | A later scoring integration must receive its own review |

The next integrity gate is an authenticated scorer that accepts only this distinct
lineage contract, carries all source digests into its report, and still cannot
promote a routing policy until the live empirical and operational gates pass.
