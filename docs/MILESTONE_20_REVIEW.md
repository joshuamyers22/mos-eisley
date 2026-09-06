# Routing activation eligibility review

Scope: derive short-lived route eligibility from the fully authenticated evaluation
chain and separately signed operational inputs. No provider query, deployment,
configuration mutation, runtime activation, traffic, or publication is included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| A lax cost/freshness policy is substituted locally | Domain-separated Ed25519 signature binds the exact activation policy; the operational snapshot binds its digest | Authority-policy distribution and policy-signing judgment remain trusted |
| A passing operational snapshot is reused with a different routing policy | Snapshot binds candidate policy, promotion receipt, activation policy, exact routes, and pricing basis | Signer assertions and referenced evidence are not independently fetched |
| One evaluator controls promotion and activation | Every activation identity/key must be disjoint from all graders, resolvers, and promoter | Identity declarations do not establish organizational independence or prevent collusion |
| One activation key supplies every approval | Policy, readiness, and control require three distinct enrolled identities and keys | The trust policy does not encode narrower per-key roles or a general quorum scheme |
| An unavailable route is silently replaced | Exact selected and required fallback routes must match; substitutions and extras fail closed | A future runtime must preserve the same invariant |
| Missing price, conformance, or drift evidence passes | Every exact route requires pass/available statuses, evidence digests, matching basis, and signed cost within its ceiling | Digests authenticate references, not truth, provenance, or measurement quality |
| Stale evidence grants indefinite eligibility | Explicit UTC windows, maximum evidence age, and earliest-deadline receipt expiry | Host clock is trusted |
| A stopped or revoked policy remains eligible | Fresh signed control state checks emergency stop, policy/promotion revocations, and minimum sequence; the follow-on pinned local anchor rejects older-message replay | Whole-anchor rollback still needs an external latest-state witness |
| Eligibility is mistaken for deployment authority | Receipt schema fixes runtime and configuration authorization to false; no runtime consumer or mutation path exists | Downstream systems must fully verify sources rather than trust standalone JSON |
| Private signing keys leak through the command | CLI accepts signed inputs and public trust policy only | External signer implementation and key custody are operator responsibilities |

## Adversarial findings incorporated

The initial design signed readiness and control but left the cost ceilings and
freshness windows as an unsigned local input. That allowed a valid evidence signature
to be combined with a lax replacement policy. The implementation now requires a
third distinct policy signature, pins that signed artifact into the receipt, and
binds its policy digest into the readiness snapshot. A regression test attempts both
signature reuse and recombination with a legitimately signed different policy.

The review also rejects stronger claims than the implementation supports. Catalog,
price, conformance, and drift values are attestations, not live provider checks.
Normalized pricing is basis-specific, and control freshness is not proof of global
latest state. Those boundaries are part of the public contract rather than hidden
behind an `activation_eligible` label.

The next gate is now implemented as a pinned local monotonic control anchor and
read-only runtime preflight. A separately authorized transaction still requires an
external latest-state witness, atomic install/rollback design, stale-head protection,
and post-activation monitoring.
