# G4 production coding-child broker architecture review

- Scope: one new provider-capable G4 correction-child adapter plus exact-offer
  preview and offline fixture tests; current branch/worktree only.
- Reviewer: Codex self-review; this is not independent launch approval.
- North star: separately approved provider use and measured local spend must
  produce a scoped child-signed proposal without extending write/acceptance powers.
- Runtime: Python 3.12+, trusted host transport/ledger/key and immutable-image,
  no-network, no-mount worker.

## Dependency and critical path

The read-only offer preflight replays custody, candidate, correction and Git
evidence. A separate creator signature names the exact offer, provider request,
model/effort, pricing, ledger, image and child. The host reserves an entry keyed
by the signed grant, then a request-bound claim passes through the isolated
worker. The host-owned transport counts and creates one response under the
pre-reserved controller. Only a completed, tool-free response with valid scoped
replacement JSON becomes an enrolled-child signature. Private audit, response
and spending bytes replay against the offline dispatch receipt. Integration,
renewed tests and acceptance remain downstream.

## Findings and disposition

| Severity | Evidence / consequence | Disposition |
|---|---|---|
| High | Existing dispatch grant explicitly denies provider use and its usage was child-reported | Added distinct creator-signed provider grant, conservative ledger settlement and separate receipt |
| High | Exact provider approval could not be prepared before the dispatch claim | Extracted read-only offer preview from the same preflight dispatch reuses; equality regression |
| High | Repeated process could spend the same grant | Ledger entry ID is the signed grant digest; cross-instance duplicate regression |
| High | Invalid response after a paid call might falsely appear successful or free | Settle or retain exposure before parsing; reject invalid proposal and prohibit retry |
| High | Provider output could spoof signature, path or usage | Provider output is parsed, scoped and measured by host; enrolled child key signs only a valid proposal; worker revalidates |
| Medium/open | Trusted host/transport/key, Docker image and upstream usage remain outside independent proof | Retain as explicit launch-review assumptions; no live authority from this code |
| Medium/open | Crash after reserve can leave a held entry or partial private run | Preserve for inspection; never auto-release or retry |

## Verdict

The offline broker boundary is suitable for no-network fixture testing after
the linked checks. It is not an independent production sign-off or authorization
for an actual provider call. The renewed G4 chain, critic quorum, final creator
and reviewer suites, and accountable implementation review remain separate.
