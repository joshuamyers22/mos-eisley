# Threat model: G4 offline correction-child dispatch

- System/version: G4 seventh offline slice, schema-1 dispatch approval and proposal.
- Owner/reviewer: Joshua Myers; accountable production review still required.
- Trigger: new boundary from evidence-only cycle admission to child proposal dispatch.
- In scope: local claim, signatures, scoped source disclosure, container validation,
  replay and receipt. Out of scope: live provider, physical key custody, Git writes,
  billing settlement and final acceptance.

| Asset | Need | Owner |
|---|---|---|
| Approved plan, tests and correction admission | Integrity and non-substitution | Creator/controller |
| Bound implementation source | Confidentiality and exact revision | Repository owner |
| Child proposal and usage claim | Authenticity and bounded size/scope | Child/controller |
| One-use claim store | Integrity and availability | Local controller |

Actors are creator, enrolled child, judge, controller, offline proposal source and
Docker daemon/image. The proposal source is a trusted host adapter; it receives
only the explicit offer as an argument, but arbitrary adapter code is **not**
sandboxed by this module. The container worker receives only canonical stdin and
has no host mount/network. The same-UID host, local clock, enrolled key custody,
Docker daemon and exact image remain trusted.

| Abuse case | Control/evidence | Residual risk |
|---|---|---|
| Reuse admission as child authority | Separate creator-signed dispatch order, exact admission/source/image links | Forged or stolen creator key |
| Replay or concurrent duplicate child dispatch | One task/cycle-specific `O_EXCL` private claim before source invocation | Multiple stores or same-UID tampering bypass local boundary |
| Child changes tests, unowned files or substitutes source | Existing bound-file allowlist, separately signed read-only creator-test view, signed proposal, immutable package/receipt replay and post-run Git check | Prior creator-test-suite hash is still a claim; no proof of arbitrary code semantics or new files |
| Wrong child or altered proposal | Enrolled child signature over exact offer and replacements | Physical child-key custody unproven |
| Exfiltration through worker | No mounts, network or credentials; only explicit owned source enters stdin | Trusted host proposal source can mishandle the offer |
| Provider/cost overrun | Provider authority false, async deadline, reported usage ceiling | No measured spend; a malicious host adapter can ignore policy |
| Crash, timeout, malformed output | Claim stays spent; bounded canonical worker input/output | Manual recovery/inspection required |
| False acceptance from passing proposal validation | Receipt denies acceptance and host writes | Final whole-suite and independent review remain open |

Required pre-production actions: review the concrete proposal/model broker and
key custody, prove measured aggregate spending and cancellation, add isolated
write/integration and full final verification, and run independent adversarial
review against the exact image and host configuration. No production activation
follows from this offline record.
