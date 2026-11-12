# rc.17 snapshot and both-store scoped live-memory review

Disposition: **refreshed snapshot passed once** on actual macOS 15.1 arm64,
UID 501. Together with the prior separately authorized SQLite case, both local
backends pass this scoped live-memory protocol. R16-02 and publication remain
separate; no general workflow, platform, privacy or billing approval follows.

## Review, authority and subject

PR #383 at `7b4ca5bf2515e9411d6a54d056c98b0fa2e754b1` passes all 14 exact-head
checks. Owner-directed review finds no blocker in its five documentation/index
files: new request/private environment/rehearsal bindings match, old snapshot is
preserved/superseded, and target-access limits remain explicit. The draft is marked
ready and merged normally as `965c7bc0adabbf691b65451de70df70f4d195e89` at
2026-11-12 02:04:30 UTC. No protection bypass, self-authored GitHub approval or
independent-human attestation is claimed.

The current owner separately approved exact refreshed snapshot `a07ee544…`, then
explicitly requested native sign-in verification and its six-call execution.
This is new authority for that request, not reuse of the old unapproved snapshot,
prior SQLite scopes, historical grants or a proposed digest. Fresh installed-native
status passes for both admitted clients under the exact captured environment.
The operator does not read credential caches or copy credentials. Status does
not independently attest remote account identity or billing. The approval record
states when processing recorded the owner instruction; it does not invent a
user-message signature/timestamp. Expiry is conservatively bounded from the first
current-turn review observation, and campaign/grants are capped by that expiry.

Subject: signed unpublished `0.1.0-rc.17`, epoch 2, source
`e6b1d75cc4140b7fb31c4a7a36fcdaf931c8f481`.

| Binding | SHA-256 |
| --- | --- |
| Exact snapshot request | `a07ee544d60d6bec819df15f85981e590160ae7a0be15d6d5de36c2b0f9df40a` |
| Unchanged execution controller | `3d7ce25146f10ef0c8c4e03d93186a5fef86ffbd2390018d0b328bc0cf8f07ea` |
| Enrolled signed metadata | `3caccc95f4d4899a5aed114e504b552b90dd1c1316c445248777d7d42d0d324f` |
| Native macOS ARM executable | `26fd7540464e0aa8fb5fb96cc2664d617ece92ec020509b00adba76ba5843a58` |
| Native environment | `b68d2414d6dab1057595eb1b50287d0960e82c5f28b87a226007d9c2211c28af` |
| Private environment-file bytes | `5d273b8e33dbb8d8e5dec95d74c8aa93d2cb0b7d08a78d3aa24582316418f8ea` |
| Full private snapshot receipt review | `7183ee8766523709780755c99fca05c93e4df5fa00756f6830c9c9aca7ba4f0b` |

## Snapshot results

| Requested profile | Dispatches / completions |
| --- | --- |
| Codex 0.163.0, `gpt-6-sol` / medium | 3 / 3 |
| Claude 2.1.283, `claude-sonnet-5` / high | 3 / 3 |

Both providers pass selected synthetic user/project memory; passive new-process
cold resume without a call/state mutation; contextual follow-up; changed-memory
refusal before dispatch with unchanged state/count; explicit refresh and one
further response; and explicit memory-off persistence with no further call.
Off persistence does not establish a fresh memory-off native outbound request or
erasure of earlier conversation history. There are no tools, repository reads,
new OS users or Docker authoring/review workers in this protocol.

The supervisor observes controller exit 0 at 70 monotonic seconds, including up
to one 35-second poll interval. This is not per-call latency. Exactly six usage
slots and six native completions verify; all saved attempts replay for evidence
verification, without re-executing inference. There are no uncertain attempts,
operator retries, repairs or API fallbacks. Both fresh usage scopes exhaust at
3/3 and differ from the previous SQLite scope identities. Native billing/internal
retries are unverified; `billing_verified=false` is retained and no precise USD
cap, settlement, vendor request count or general reliability rate is claimed.

Limits stay six aggregate/three per provider; 120 seconds/native call, 16,000 input
bytes, 8,000 accepted text bytes, 8,192 reported output tokens; 20-minute campaign
and at-most-one-hour owner approval, with grants expiring by the earlier deadline.
All 419 installed runtime Python files match the frozen signed candidate after
execution. Old snapshot `78f547…` has no live directory or approval; it is not
retried. All prior SQLite receipt hashes remain unchanged. Signed artifacts,
default client pointers, network/guest configuration and publication are unchanged.
Private synthetic fixtures and scoped usage evidence are retained for review;
public evidence contains bounded assertions/hashes, not prompts, model outputs,
raw environment values or credentials. Earlier failures remain retained.

## Both-store reconciliation

The [machine aggregate](qualification/rc17/both-store-memory-review.json) binds
the [prior SQLite result](RC17_SQLITE_MEMORY_QUALIFICATION_REVIEW.md) and
[snapshot result](qualification/rc17/snapshot-memory-live-review.json): twelve
application-authorized native invocations, twelve completions, zero uncertain
attempts, four distinct exhausted three-call scopes, no operator retry/repair/
fallback. Each backend has its separately frozen request/environment and owner
approval. These are not a single identical-environment campaign or independent
evaluation samples; no prospective eligibility or study claim is made.

This closes only the named local both-store memory/chat/cold-resume/refusal/refresh/
off-persistence boundary. It does not qualify full memory-enabled coding through
review/creator approval/integration/fresh tests, actual memory-off native payload
exclusion, default/client/tool-descendant egress, API authentication/inspection,
direct review, remote OS/native-auth/containment or the remaining privacy/operations
composition. Historical rc.14 workflow evidence and its uncertainties remain
historical. Stable-v1 and publication are not approved.

## Reachable console and remaining access

The owner-account overlay Mac remains online. The new bounded strict SSH probe
returns connection refused; a single banner-only connection detects the VNC
protocol on its Screen Sharing service. The native Screen Sharing application is
opened for owner-local authentication. No credentials, screenshots, guest commands
or configuration changes are used to obtain that observation. The private route
is supplied directly to the owner; addresses and private device identifiers are
not published here.

A reachable service/opened client is not verified owner login, architecture or
native-client/Docker readiness. The Mac is not yet labeled Intel or qualified.
The owner must complete local authentication and supply a permitted SSH route or
owner-operated console preflight. Existing local Linux/Windows VM registrations
remain invalid; actual Linux x86_64/arm64 and Windows-hosted WSL2 login/console
arrangements have not been supplied. Their final execution packets stay unbound.
No target identity, native authentication or guest image is inferred from labels.
Publication and any further live case require their separate gates/authority.
