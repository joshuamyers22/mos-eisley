# G4 correction-child dispatch architecture review

- Scope: offline dispatch boundary after commit `f8544c9`; new dispatcher,
  contained validator, correction-claim verifier and regression tests.
- Reviewer: Codex self-review only; **not** independent production approval.
- North star: exact one-use authorization for one adjudicated correction, with
  no host write, provider call or false acceptance.
- Runtime: Python 3.12+; immutable no-mount `OfflineContainer` in product path.
- Budget: two evidence-changing passes; stop before live/provider or write activation.

## Dependency and critical path

`dispatch_correction_child` consumes the prior correction claim, candidate receipt,
authenticated provenance, controls and binding. It snapshots the complete bound
implementation inventory, then offers only approved existing owned files to an
injected offline proposal source. It also supplies the exact digest-matching
approved plan and the assignment's concrete
creator-test files under a separate creator-signed view digest, without allowing
test replacement. The child signs its returned replacement set.
Host policy validates signatures, scope and allowance, then the immutable container
repeats deterministic proposal validation. The host compares results and replays
Git before returning an evidence-only receipt. The only durable state transition
is an exclusive task/cycle claim outside Git; the proposal source and container
never receive a host repository path or write authority.

## Findings and disposition

| Severity | Evidence and consequence | Disposition |
|---|---|---|
| High | Prior cycle admission explicitly denies child dispatch; using it alone would bypass creator authorization | Added separate domain-signed exact dispatch order |
| High | Claim keyed by signed-order digest would permit a second order for the same task/cycle | Key claim by task ID and cycle instead |
| High | Unsigned or wrong-child proposal would sever provenance | Require enrolled child signature over exact offer and proposal |
| High | Source-only offer withheld the creator tests and approved plan from the child | Bind plan bytes to the original digest and add a separately creator-signed, read-only creator-test byte view |
| High | Synchronous proposal callback could outlive the cycle allowance | Use cooperative async timeout, then bounded container timeout; concrete adapter still requires cancellation review |
| High/open | Callback is trusted host code and usage is self-reported; no real spend enforcement or provider adapter | Keep provider authority false and deny production activation |
| Medium/open | No host Git integration means proposal validation alone cannot complete correction | Keep final chain, tests and acceptance as separate gates |

## Verdict

Offline evidence-only dispatch can be exercised under fixture substitution after
the listed checks. Production release is **blocked** pending a concrete provider
broker, measured spend, real custody, isolated write/integration and independent
review. No claim is made that a signed proposal or model agreement is correct.
