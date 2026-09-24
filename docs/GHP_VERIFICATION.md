# GHP verification-loop closure

Risk class: high-risk external publication and credential boundary.

| Perspective | Evidence-changing pass | Result |
|---|---|---|
| Requirements and architecture | Compared stock GHP, an outer-proxy composition, a maintained fork and a direct short-lived GitHub App publisher. | Direct publisher remains the smaller candidate; stock GHP rejected. |
| Source-policy inspection | Traced token creation, REST/GraphQL routing, audit emission, codeload behavior and revocation cache semantics at the pinned commit. | Three enforcement blockers and several secondary gaps reproduced. |
| Build and implementation tests | Full race suite with PostgreSQL/Vault, two clean builds and distroless smoke test. | Tests passed and binary was reproducible. |
| Dependency security | Official `govulncheck` v1.8.0 on the exact source/toolchain. | 27 reachable findings; gate failed. |
| Deployment/network inspection | Not performed after the G1 stop gate. | No deployment claim. |
| Independent security/operations acceptance | Not requested after the candidate failed technical prerequisites. | No acceptance claim. |

Blocking threshold was reached by open-scoped token issuance, route fail-open
behavior, unauditable writes and reachable vulnerable code. Repeating deployment or
publisher passes against the same evidence cannot cure those properties. The loop
therefore terminates with the no-go decision in
[`adr/0005-ghp-github-publication-boundary.md`](adr/0005-ghp-github-publication-boundary.md).

Re-entry requires a new exact upstream revision or a separately approved design;
it is a new evidence loop, not a continuation that inherits this candidate's
positive test results.
