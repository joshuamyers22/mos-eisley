# Milestone 91: Held-reservation credentialed transport

## Disposition

Accepted as the transport primitive for the next live OpenAI calibration boundary.
`PreReservedOpenAITransport` consumes one already-held, exact reservation; it never
creates a second reservation, checks the held ledger entry before token counting and
again before generation, and settles or marks the same entry exactly once.

## Adversarial findings

| Risk | Control | Remaining boundary |
| --- | --- | --- |
| A stale or altered hold is used | Reservation and ledger digests, amount, policy, request, and `held` status are rechecked | The caller must verify the signed prepared execution and fresh consent |
| A request exceeds its envelope | Counted input and response usage are bounded before settlement | Provider billing evidence remains observational until reconciliation |
| A transport or process failure is retried | One-use latch and `uncertain` settlement retain the full hold | Recovery of uncertain entries is a separate operational workflow |
| A second reserve silently charges twice | The pre-reserved path never calls `ledger.reserve` | Ledger durability and operator backup remain deployment concerns |

No live provider call is made by this milestone's tests. The credentialed CLI path is
available only after complete offline verification and explicit transfer consent.
