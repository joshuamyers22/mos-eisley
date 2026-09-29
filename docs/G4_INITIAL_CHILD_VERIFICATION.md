# G4 initial-child offline verification

- Scope: initial-child offer, one-use dispatch, no-network worker, exact live
  broker and receipt replay; no real provider call in these checks.
- Implementer/reviewer: Codex implementation and self-review; Joshua's separate
  exact signatures and live grant are required for production qualification.
- Frozen inputs: approved bounded-quote plan/tests and base `699f345…`; a new
  policy and package custody are being prepared because the old policy expired.

| Claim | Check | Result |
|---|---|---|
| New initial artifacts cannot be mistaken for correction artifacts | Separate schema kinds and signature domains | Focused validation passes |
| Read-only preview rejects stale plan, changed creator tests and dirty Git | Disposable signed custody and Git fixture | Focused test passes |
| One assignment cannot dispatch twice | Exclusive private claim | Focused test passes |
| Child cannot edit tests, exceed limits or use another key | Enrolled-signature and scope tests | Focused test passes |
| Offline worker independently validates canonical signed proposal | Worker subprocess fixture | Focused test passes |
| Paid malformed provider output yields no signed result | Fake transport and ledger fixture | Focused test passes |
| Successful live-broker fixture measures, settles and replays one response | Fake transport, audit and receipt replay | Focused test passes |

The focused tests and static checks cover implementation behavior only. A real
initial-child path is not qualified until the fresh owner signatures, immutable
image, exact one-use provider grant, actual provider call, signed dispatch
receipt, isolated Git integration and downstream quality/review gates replay.
