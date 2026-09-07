# Milestone 46 adversarial review: signed conformance authorization

## Disposition

Accepted as independent, exact, short-lived authorization for one blinded OpenAI
conformance attempt. Rejected as proof of informed human consent, provider receipt,
post-run observation, billing finality, or empirical-quality evidence.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A shell flag alone authorizes paid data transfer | Require both explicit local confirmation and a verified Ed25519 authorization before API-key access | Either can still be supplied by a compromised local operator environment |
| A signature is moved to a nearby request or spending scope | Bind both policy hashes plus every assignment, request, ledger, entry, and maximum-cost identity | Authority-policy distribution and local file custody remain trusted |
| An old authorization is replayed | Bound issue/expiry to authority, conformance, and spend windows; require enough lifetime for the request timeout | Host clock compromise and same-UID rollback remain possible |
| The post-run observer pre-authorizes its own evidence | Reject every authority ID or public key appearing in the conformance observer roster | Different enrolled people can collude; organizational independence is external |
| A signature is replayed from another protocol | Use a distinct domain separator over canonical strict authorization bytes | Private-key custody remains external |
| Signing authority silently enables more operations | Literal fields authorize only one exact blinded attempt and deny unblinded transfer, retry, release, conversion, scoring, promotion, and activation | The trusted transport and local implementation remain in the execution trust base |
| A signing workflow captures private keys | CLI derives unsigned bytes only and exposes no private-key option | External signing tooling and key handling are operator responsibilities |
| Authorization derivation is described as a paid action | Emit explicit false flags for authentication, credential access, dispatch, and reservation | The later live command remains paid-capable and separately invoked |

## Verification scope

Tests cover exact signed authorization, cost and identity binding, tamper and spend
substitution, expiry, maximum lifetime, authority/observer separation, unsigned CLI
derivation without credential or dispatch, and live rejection before API-key access.
Provider and Docker behavior remains synthetic; no credentialed or paid request is
made.
