# Frozen-policy holdout evaluation review

Scope: one-attempt local evaluation of an immutable candidate policy against a
fully reverified holdout lineage. No fitting, provider calls, configuration changes,
promotion, activation, or publishing is included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| Holdout outcomes change the selected route | Recompute the frozen policy solely from its calibration chain before reading scores; report the original decision unchanged | A file owner can inspect holdout through other software |
| A favorable subset replaces the matrix | Reverify all holdout sources and require exact assignment coverage for the hard-coded holdout split | Declared group independence and dataset representativeness remain operator claims |
| Failed holdout is rerun until it passes | Atomically create a policy-keyed claim before scoring; retain it on every later failure | Another directory, copied data, claim deletion, or direct library use bypasses a local filesystem guard |
| Claim/report collision corrupts evidence | Require a pre-existing private, current-user-owned claim directory; reject overlap; create claim and report with exclusive writes | Processes with the same user identity remain inside the trusted controller boundary |
| A stronger-route narrative is invented after results | Define under-routing only as selected failure plus another permitted adequate route; do not infer an unregistered strength order | The role floor itself remains reviewed human judgment |
| Missing prices create false regret precision | Suppress cheapest-route and cost/latency regret claims if any adequate candidate lacks complete cost evidence | Meter correctness and current prices need operational validation |
| Fail-closed is hidden as quality success | Report calibrated, fallback, fail-closed, served, adequate, under-routed, and missed-alternative counts separately | Product policy must decide whether coverage is acceptable |
| A passing report becomes production policy | Literal promotion and activation denial; no runtime consumer accepts the report schema | Signed promotion, drift gates, runtime health handling, and rollback remain future controls |

The next gate is an independently authorized promotion contract with explicit
acceptance thresholds for the already-produced holdout report. It must not add a
second holdout look or reinterpret thresholds after outcomes are known.
