# G4 post-deadline integration threat model

## Scope and ownership

- System: schema-2 carry-forward approval for one completed correction-child proposal.
- Owner and accountable signer: Joshua Myers; VCS attestation uses his enrolled key in the disclosed single-operator policy.
- Trigger: the original task expired before its real-child correction was integrated.
- Scope: one offline detached-worktree commit. Provider calls, original checkout writes, final testing, acceptance, merge and push remain outside this authority.

## Assets and trust boundaries

| Asset | Integrity need | Control |
|---|---|---|
| Historical child, candidate and correction evidence | No alteration or backdating | Full old-chain replay and exact receipt hashes |
| New integration authority | Current, exact creator consent | Fresh policy window, separate v2 signature domain, bound store and proposal |
| Target Git repository | Only child-owned source replacement in a detached worktree | Existing tree, path, blob, parent, patch and clean-checkout checks |
| One-use claim | No silent retry or store substitution | Store path hash in approval and exclusive private claim |

The private same-UID host, enrolled public keys, signed historical evidence and
fixed Git executable remain trust inputs. A renewed policy may change only its
identifier and validity window; all role keys and operator mode must match the
historical policy. The creator signature binds the renewed policy hash.

## Abuse cases and controls

| Abuse case | Impact | Control and evidence |
|---|---|---|
| Treat expired task as current | Unauthorized write | v1 path still rejects expired task; v2 requires issue after old deadline and its own current window |
| Substitute proposal, source, paths or store | Write wrong bytes or replay grant | Exact signed links, source replay, store hash and one-use claim; negative tests |
| Substitute signer or signature domain | Impersonated grant or VCS record | Identical enrolled key roster and separate v2 Ed25519 domains; wrong-domain test |
| Alter source or protected tests before write | Commit on stale evidence | Candidate/provenance and clean-tree replay before claim; post-commit original-tree replay |
| Crash after claim or partial Git write | Ambiguous state | Stop without retry; preserve private claim/worktree for inspection |
| Misstate acceptance | Premature G4 completion | Record fields deny final tests, independent review and acceptance |

## Decision and residual risk

The new signature is an explicit offline write decision. It does not renew the
original provider budget or authorize another child call. The host and private
store remain trusted; a malicious same-UID operator or compromised enrolled key
can still undermine local evidence. Human review of the exact approval and
post-commit VCS record is required before claiming the integration gate complete.
