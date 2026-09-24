# Threat Model: G4 candidate execution admission and dispatch

## Scope and ownership

- System/version: G4 candidate approval, admission and one-use offline dispatch v1.
- Owner: Joshua Myers; implementation by Codex; accountable review still required
  before production candidate use.
- Date and review trigger: 2026-09-24; re-review on signer, Git, image, storage,
  test-runner or authority-contract changes.
- In scope: exact approval, source/control replay, local one-use claim, isolated
  candidate tests and immutable receipt. Out of scope: coding-child dispatch,
  correction, final whole-suite review, model/provider calls and acceptance.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Creator signing key | secret | uncompromised and outside repository/CLI | enrolled creator |
| Frozen package, binding, controls and provenance | private evidence | exact canonical bytes and lineage | controller/reviewer/VCS custody |
| Candidate source revision and Git objects | implementation | exact committed identity and clean bound worktree | trusted VCS broker |
| Dispatch claims and receipts | private control/evidence | exclusive claim, durable retention | trusted host controller |
| Docker image/daemon and kernel | privileged execution base | exact image, no-mount/network-disabled containment | operator |

- Actors: enrolled creator, trusted host controller, untrusted candidate/test code,
  potentially malicious same-UID actor, and corrupted or stale artifact supplier.
- Boundary: untrusted signed/artifact bytes enter strict canonical decoders; current
  Git enters the read-only broker; one exact request crosses into the immutable
  container; the controller-owned claim crosses a local persistence boundary.
- Dependencies: prior G4 package, binding, isolated control and authenticated
  provenance contracts; local UTC clock; fixed Git and Docker executables.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Reuse prior provenance as candidate authority | attacker has earlier record | unauthorized execution | separate domain-signed creator approval; generic runner rejects candidate | unsigned-run regression | direct malicious trusted-host code can call internal functions |
| Swap source, image, controls, request or signer | artifact supplier controls input | wrong code/test run | signed exact hashes, enrolled key, current read-only Git replay and image equality | substitution and stale-tree regressions | compromised enrolled key or Git/image base |
| Replay or concurrent double dispatch | valid approval copied | duplicate untrusted execution | exclusive claim per approval in private persistent controller store; failures consume claim | replay and store-permission tests | alternate store or deleted claim bypasses local guard |
| Repo or lifecycle write through input paths | malicious path selection | mutate source/evidence | library and CLI require private paths outside Git; no host test fallback; container has no mounts | location checks and isolation contract | same-UID host compromise |
| Crash between claim and receipt | process failure | ambiguous completion | claim remains spent; no automatic retry; new signed approval required | state-machine contract | manual recovery and forensic review required |
| Candidate suite error masked as pass | malformed worker observation | false success | canonical worker receipt, exact counts/IDs, candidate role expectation and post-run input/Git replay | failed-candidate regression | malicious trusted worker/image |
| Expired or pre-child approval | stale time/order | stale dispatch | UTC policy/window and child-result chronology checks at dispatch | window regression | local clock can be wrong or controlled |
| Data exfiltration or credential access | malicious tests | private-data loss | only declared bytes enter network-disabled, no-mount container; no credentials passed | inherited isolation tests | Docker/kernel/image compromise or timing/resource side channels |
| Input amplification or DoS | oversized artifacts/tests | resource exhaustion | bounded decoders, 5–60 s request, container limits, one-use claim | prior runner tests | trusted-host Git replay cost and local disk pressure |
| Insider resets store or signs dishonest facts | privileged operator | unauthorized repeated run or false custody | explicit trust assumptions, retained claim and owner review | audit records | no external monotonic witness or independent human proof |

## Decisions

- Accepted risks: Joshua Myers owns the single-operator and same-UID/local-clock
  limits. They do not permit a production launch or independent-review claim.
- Required tests and monitoring: exact approval, role/signer substitution,
  expiry, dirty bound source, private-store mode, duplicate claim, failed result,
  receipt replay, and installed-wheel CLI smoke. Alert on spent claims without
  receipts and on repeated duplicate dispatch attempts in any operational wrapper.
- Recovery: preserve spent claims and partial evidence. Never delete a claim to
  retry; issue a fresh approval after root-cause and current-input revalidation.
