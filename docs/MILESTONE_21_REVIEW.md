# Routing runtime preflight review

Scope: maintain monotonic local routing-control state and produce a read-only,
short-lived preflight after full evidence verification. No provider request,
configuration change, route installation, traffic dispatch, or publication occurs.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| A still-valid older control message is replayed | Preflight requires exact equality with the latest fully verified anchor entry | Whole-database rollback or cloning by the owner requires an external monotonic witness |
| An attacker supplies a fresh replacement anchor | Signed activation policy pins the complete anchor-policy digest, including unique identity, trust-policy digest, and control signer roles | An exact clone with the same policy is indistinguishable locally |
| A policy/readiness signer advances revocation state | Anchor policy explicitly restricts control signing to enrolled identities | Enrollment and organizational identity remain external roots of trust |
| A higher sequence removes an earlier revocation | Every append reverifies history and requires both revocation sets to be supersets | Emergency stop can be cleared by an authorized higher state; no separate resume quorum exists |
| Rows are reordered, deleted, or altered | Canonical entries are hash-linked, sequence keyed, synchronously committed, and fully audited on each operation | Same-UID replacement with a recomputed or older internally valid database is outside the local boundary |
| A stale or future control is anchored | Ingestion requires explicit UTC currentness, advancing issuance time, and nondecreasing anchor time | Host clock remains trusted |
| Preflight skips prior gates | It reconstructs activation eligibility, which recursively reconstructs promotion, holdout, calibration, and signed evaluation lineage | Operational evidence remains attested rather than fetched |
| Passing preflight is treated as permission to send | Schema fixes dispatch, runtime activation, and configuration mutation to false | A future transaction must define one-use authority and atomic stale-state recheck |

## Adversarial findings incorporated

The first design keyed the anchor only by its path and activation trust policy. A
different database could therefore reset the latest sequence. The final design
requires the complete anchor policy to be created before activation-policy signing;
its digest is bound into the activation policy, eligibility receipt, and preflight.

That change does not make local storage globally rollback-proof. The review therefore
narrows the claim from “external latest state” to “latest state in the pinned intact
local anchor.” The remaining bootstrap, whole-file rollback, and post-preflight race
are explicit blockers for dispatch authorization rather than undocumented caveats.

The next safe boundary is a one-use dispatch grant issued by a trusted broker that
atomically checks an external latest-state witness, exact preflight and route, current
spending admission, and provider catalog immediately before one request. It must not
install a general routing policy or give a model configuration authority.
