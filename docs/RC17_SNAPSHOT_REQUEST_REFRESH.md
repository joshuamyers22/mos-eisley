# rc.17 snapshot request refresh and target-access review

Status: **prepared, not authorized or executed**. Owner: Joshua Myers; operator:
Codex. Date: 2026-11-11 owner local time. Publication remains separate.

PR #382 at `b6ce5e6a985b907862def86426740df0288c2874` passes all 14 exact-head
checks after its original source/package runs finish. Owner-directed review finds
no blocking issue: seven documentation/index files, matching retained private and
public SQLite evidence, six completed turns, correct billing/latency limitations
and explicit remaining gates. The draft is marked ready and merged normally as
`6304e598327a205377d1ba479c282740dbd8b3a3` at 2026-11-12 00:49:54 UTC. No admin
bypass, workflow retry or independent-human attestation is claimed. The completed
SQLite scopes remain exhausted; no earlier uncertainty or failure is relabeled.

## Separate snapshot request

The original unapproved snapshot request
`78f547c499e86c996ac9aa40b34988787615f969801b2e436c335294d6627365` fails the
current environment binding preflight. Candidate, controller, native clients,
authentication locations, actual owner and OS still match; the specific changed
environment variable is not inferred from a hash. No model call, real grant or
live directory is created by the failed preflight. Preserve the old request;
do not alter it or try to reconstruct an old environment to force its digest.

Current request: `R17-MEM-SNAPSHOT-5cd0735813d9`.

| Binding | SHA-256 |
| --- | --- |
| New exact request | `a07ee544d60d6bec819df15f85981e590160ae7a0be15d6d5de36c2b0f9df40a` |
| Unchanged execution controller | `3d7ce25146f10ef0c8c4e03d93186a5fef86ffbd2390018d0b328bc0cf8f07ea` |
| Current native environment | `b68d2414d6dab1057595eb1b50287d0960e82c5f28b87a226007d9c2211c28af` |
| Private environment-file bytes | `5d273b8e33dbb8d8e5dec95d74c8aa93d2cb0b7d08a78d3aa24582316418f8ea` |
| Request-specific offline preparation review | `b52585e9c0ff6c18aa3fef2867f557d0eb720096332afbe3ac032c69e1967e17` |

Subject stays signed unpublished rc.17, source
`e6b1d75cc4140b7fb31c4a7a36fcdaf931c8f481`, on actual local macOS 15.1 arm64,
UID 501. Native executable SHA remains
`26fd7540464e0aa8fb5fb96cc2664d617ece92ec020509b00adba76ba5843a58`;
metadata remains `3caccc95f4d4899a5aed114e504b552b90dd1c1316c445248777d7d42d0d324f`.
The refreshed request has new synthetic identifiers, sessions and private roots.
It pins the actual current allowlisted environment privately, rather than
weakening the controller's hash check or publishing environment values. Allowed
fields are HOME, LANG, LC_ALL, LOGNAME, PATH, TMPDIR and USER; no credentials or
credential-cache contents are captured. No default client, native sign-in, VM,
network configuration, product code or signed artifact is changed.

The original limits remain: six total native invocations, three/provider; Codex
0.163.0/gpt-6-sol medium and Claude 2.1.283/claude-sonnet-5 high; 120 seconds/call,
16,000 input bytes, 8,000 accepted text bytes, 8,192 reported output tokens;
20-minute campaign capped by fresh owner expiry, with grants expiring by the
earlier campaign/owner deadline and no more than one hour after approval. Only
synthetic selected memory and fixture history transfer; no tools, repository
reads, operator retries, repairs or API fallback. Native billing/internal retries
remain unverified and are not a precise USD cap. Explicit off persistence is a
zero-dispatch check, not a fresh memory-off outbound request.

A new signed-installed fake-client rehearsal passes six fixture dispatches, zero
live calls. Downstream preparation review binds the new request/environment and
controller, verifies fake-client-only grants, all six saved attempts, fresh
request-specific memory identifiers and off persistence. Original generic result
receipts alone are not claimed to identify a unique request. No model outputs,
prompts, raw environment values or credentials are included in public records.
[Machine metadata](qualification/rc17/snapshot-memory-request-refresh.json) and the
[request index](qualification/rc17/fresh-live-requests.json) remain non-authorizing.

Fresh owner approval of this new digest, data transfer and native billing/retry
exposure, plus just-in-time client-owned sign-in checks, are required before real
grants or execution. Old snapshot approval references and completed SQLite scopes
cannot authorize this request. The current step prepares a separate approval
request; it does not manufacture consent or start another live campaign.

## Actual target-access findings

Read-only discovery checks SSH configuration, repository self-hosted runners,
existing Parallels registrations and owner-account Tailscale device metadata:

- No configured SSH aliases and no self-hosted repository runners.
- Two local Parallels registrations report invalid status; neither is started,
  repaired or claimed to be an accessible guest. A VM label is not OS/architecture
  or actual WSL2 proof, and the Linux label does not match the frozen Ubuntu 22.04
  qualification baseline.
- One owner-account Mac mini is online in the overlay inventory. A single bounded
  SSH probe, using native defaults, strict host-key checking, no password prompts
  and no configuration changes, times out on port 22. No guest command or native
  provider call executes, and no architecture/login identity is verified.

Device addresses, private host identifiers and account/credential data are not
published. These observations establish **zero verified access targets**; they do
not prove a firewall/service/root cause. The owner must supply a reachable login
or console arrangement for the Mac candidate and actual Linux x86_64/arm64 and
Windows-hosted WSL2 targets. No borrowed credential, newly provisioned cloud host,
hosted-CI substitution, native Windows support, architecture or target identity
is inferred. Final remote qualification packets remain unbound.

## Verification and stop

Selected guidance: AGENTS, adversarial/agentic guides, threat-model and work-note
templates, frozen v1 profile and existing request contract. Resource ceiling:
one read-only exact-head review/normal merge, a two-hour CI tracking window,
one request refresh/rehearsal, bounded metadata-only access probes and zero new
provider invocations. Passing gates: exact 14-check CI; matching SQLite retained
receipts and scope; new request/environment/client/candidate pins; request-specific
fake rehearsal and documentation/JSON consistency. Stop live work for unbound
access, stale authority, unexplained required failure or missing owner consent.
All first failures and original requests stay retained. R16-02, other missing
profiles and publication remain separate.
