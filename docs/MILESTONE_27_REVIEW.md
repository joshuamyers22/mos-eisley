# Milestone 27 adversarial review: skill-release control

## Disposition implemented

Add independent signed allow/revoke control over one exact release-evidence artifact,
permit exact retained rollback nomination only on revocation, and pin the latest state
in a private monotonic anchor. Preserve the boundary as non-installing.

## Adversarial findings addressed

| Attack or ambiguity | Disposition | Remaining limit |
|---|---|---|
| A promotion authority approves and controls its own release | Reject every control-policy ID or public key that overlaps promotion, grading, or resolution | Enrollment and real-world independence remain operator assertions |
| A signature is moved to another package, release, policy, or rollback target | Domain-separated signature covers every exact digest, identity, disposition, sequence, and UTC bound; authentication deterministically recomputes them | Trust-policy distribution and key custody remain external |
| A same-name or version-labeled package is substituted as rollback | Embed and semantically reverify complete retained bytes; require a different exact package for the same source-qualified persona name | Content identity does not establish authorship or safety |
| A still-valid older allow message is replayed after revocation | Anchor the exact release, require increasing sequence/time, exact latest-state equality, and irreversible revocation | Whole-database rollback or cloning needs an external monotonic witness |
| A high arbitrary sequence creates false security at bootstrap | Anchor policy pins a minimum sequence rather than trusting first-seen state alone | The policy itself must be distributed through a trusted channel |
| A stale decision is accepted | Policy, release evidence, and decision windows all bound validity; CLI authentication and anchor advance use host UTC | Host time has no external witness |
| Rollback nomination is mistaken for deployment permission | Decision, policy, receipt, archive, and anchor events retain literal installation/activation/configuration denial | Transactional installation and runtime consumption remain unimplemented |
| In-process model copying bypasses archive literal validation | Semantic archive verification now independently rejects any deployment-authority bit | The Python process and loaded code remain trusted |

## Stop condition

This milestone stops before filesystem materialization. It adds no installer,
configuration writer, runtime skill selector, or drift monitor. The next safe slice is
a separately reviewed transaction protocol with exclusive destination ownership,
staging, exact post-write verification, atomic switch, crash recovery, and an
external latest-state witness or explicit acknowledgement of its absence.
