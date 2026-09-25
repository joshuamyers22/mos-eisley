# G4 first qualification preparation threat model

## Scope and ownership

- System/version: `g4-q1-quote-half-up` offline packet, 2026-09-25.
- Owner: Joshua Myers. Review trigger: preparation for the first real G4
  correction-path exercise after approval of the gate code at `752c350`.
- In scope: controller/image and target identity, draft plan/test custody,
  authority sequencing, source isolation and future spending/role boundaries.
- Out of scope: actual provider dispatch, key creation/custody, reviewer-family
  proof, invoice reconciliation, production acceptance and G3 completion.

## Assets, actors and boundaries

| Asset | Sensitivity | Required integrity | Owner |
|---|---|---|---|
| Private draft plan and reviewer tests | Blind task material | Exact hashes; never enter child offer except approved plan | Creator/reviewer custodians |
| Isolated target Git tree | Executable but disposable code | Clean base and future signed ancestry | Project owner/VCS broker |
| Controller image and artifact stores | Trusted execution/one-use state | Immutable image ID, separate private persistent claims | Project owner |
| Future signer keys, provider credential and ledger | Authority and spending | External custody, exact grants, reservation before send | Enrolled operators |

The child receives only the signed scoped offer, not reviewer tests, secrets or
ambient repository access. External critics/judge later receive the exact
post-suite subject; signatures attest enrolled keys, not actual provider lineage.
The local Docker daemon, kernel, Git object store, controller clock and same-UID
operator remain trusted as stated by the component contracts.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Control / current evidence | Residual risk |
|---|---|---|---|---|
| Send before creator approval | Draft files mistaken for authority | Unapproved child or spend | Packet explicitly has no grant; signed exact plan/tests and one-use broker grants required | Operator could bypass the product path |
| Reveal blind tests to child | Files or whole repo sent as context | Contaminated evaluation | Reviewer draft outside target; future offer allowlist and custody review | Same operator created current drafts; independence not proven |
| Substitute source or image | Mutable tag/tree | Wrong bytes tested | Clean base commit and immutable image ID; future Git and binding replay | Host/Docker or registry compromise |
| Forge initial-child provenance | Seed commit mislabelled real model output | False end-to-end claim | No pre-approval child commit; seeded path must be labelled; separate real initial-child exercise | Future attestor can still lie |
| Switch claim store or retry uncertain send | Same-UID access | Duplicate call or unbounded spend | Persistent private stores, exact grants, shared-ledger reservation, no automatic retry | Same-UID host/clock trust |
| Use only one provider family | Missing second live adapter | False independent quorum | Two-family signed roster and explicit missing-family gate | Enrolled labels do not prove real provider operation |
| Accept a test proxy as quality | Passing controls/final suites only | Wrong final implementation | Exact independent critic/judge review and creator decision; applicable G3 gate | Citation presence does not prove claim truth |
| Exfiltrate via tests or provider | Untrusted code/context | Private-data loss | No mounts/network in isolated worker; only reviewed task data in provider request | Trusted host/provider must enforce policy |

## Decisions and exit

- The owner specified a $10 task-wide cap and 2026-09-26 23:59 Eastern
  deadline, but no live provider authority or ledger reservation exists;
  actual spend remains zero until a separately signed and approved grant.
- Do not create a child commit or freeze the reviewer package against a draft
  creator approval. Do not use generated test keys as independent humans.
- Rebuild and reverify the image if code/lock/platform changes; old G2 image is
  not a G4 qualification image. Keep exact artifact stores outside both repos.
- The correction-path qualification and the entire creator-led loop are distinct
  claims. Missing signer custody, second family, G3 gate or live authorization
  keeps the latter open.
