# Threat Model: live read-only review qualification

## Scope and ownership

- System/version: Mos Eisley at GitHub `main`
  `fa0faafb6f29421e46429001be3932b614f392f0`
- Owner and reviewer: Joshua Myers, explicitly approved as the single operator for
  custody, phase authorization, observation and launch review under ADR-0005
- Date and review trigger: 2026-09-19; repeat on guidance, provider, SDK/image,
  ledger, policy, signing authority, evidence schema, or launch-flow changes
- In scope / out of scope: exact three-attempt critic/judge conformance campaign and
  one exact launch-admission decision. Authoring, machine writes, scoring, routing,
  public activation, retries, and invoice finality are out of scope.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| OpenAI credential | Secret | Never persisted; accessed only after current exact gates | Credential operator |
| Review brief and responses | Private transferred data | Exact bounded requests/results and owner-scoped retention | Project owner |
| Campaign and launch ledgers | Financial authority | Dedicated identities, conservative reservation, no reuse/release | Project owner |
| Phase, observer, and launch signing key | Accountable self-authorization | One Joshua Myers identity/key, domain-separated signatures, no independence claim | Joshua Myers |
| Campaign seal/evidence and launch decision | Security evidence | Independently pinned bytes, freshness, complete reconstruction | Custodian/reviewer |
| Worker image and lifecycle evidence | Containment evidence | Immutable identity, exact cleanup and runtime records | Runtime operator |

- Actors and capabilities: Joshua Myers as project owner, credential operator, phase
  authorizer, local approver, commitment custodian/observer and launch reviewer;
  trusted host; isolated workers; OpenAI; malicious local input/process.
- Entry points and trust boundaries: private configuration/files to strict contracts;
  signature verification; ledger transactions; host credential loader; one-use broker;
  isolated worker pipes; provider network; response/evidence publication.
- Data flows and external dependencies: seal exact no-send campaign; retain hash under
  separate custody; run fixed slots with fresh signatures and local approval; inspect
  runtime and sign observations; reconstruct all evidence; compare an exact proposed
  launch; sign and recheck launch admission at every use.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| One operator mistakes self-review for independence | Joshua controls every signing/custody role | False confidence and self-authorization | Schema-2 mode requires one shared identity/key, forbids the independent-review assertion, and requires signed self-review-risk acceptance; docs name Joshua as accountable owner | ADR-0005, signed policy/decision records and mixed-mode tests | No second human can detect Joshua's mistake, coercion, collusion or host compromise |
| Post-hoc or replaced campaign commitment | Host can rewrite local inputs | Cherry-picked successful evidence | Seal before attempts, independently retain raw hashes, fixed slots, reject replacement and starts before seal | Fresh campaign review of exact retained bytes | Malicious host rollback of all trusted inputs needs an external witness |
| Stale/substituted policy, guidance, SDK, image, request, or result | Local files/config change | Unauthorized or incomparable review | Fresh reconstruction at approvals, credential access, SDK operations, evidence and launch checks | Mutation/revocation tests and exact digests | Provider service behavior can change behind a stable client contract |
| Credential access before authorization | Flow or callback reads environment early | Secret exposure or unintended transfer | Credential loader runs only after current phase/campaign/launch/local gates and retained admission; recheck after loading | Credential-order/revocation tests | Trusted host code and same-UID memory remain trusted |
| Duplicate dispatch or automatic retry | Race, crash, timeout, or operator repeats a slot | Duplicate transfer/charge and invalid sample | One-use owned objects, consumed grants, fixed paths/slots, no resume/retry, missing slot stays missing | Concurrency/cancellation and campaign-order tests | Remote receipt can be uncertain after process/network failure |
| Ledger reuse, double reservation, or optimistic release | Wrong path/policy or partial failure | Spend exceeds approved ceiling | Dedicated empty campaign ledgers, separate launch ledger, atomic holds, exact settlement, uncertain retention | Ledger reconstruction and mutation tests | Account-wide invoice finality remains outside local evidence |
| Joshua signs host assertions without meaningful assessment | Convenience, fatigue or compromised host | Local artifacts are authenticated but misleading | Exact reconstruction, fixed slots, explicit self-review label and retained evidence; stop on ambiguity | Observer policy and signed exact observation | Human process quality has no independent backstop in this mode |
| Malformed/oversized provider data or raw error retention | Provider/proxy is hostile or fails strangely | Memory pressure, secret/private-data leakage, false success | Bounded transport, strict schemas, allowlisted failures, content hashes, private modes | Existing response, audit and secret-canary tests | Some SDK internals may buffer before local rejection |
| Worker escape or incomplete cleanup | Container/runtime compromise or cancellation race | Credential/data/host exposure | No worker credential/network authority, one-use private IPC, immutable image, watchdog and exact cleanup evidence | Real offline Docker success/cancellation probes | Kernel/container/host compromise is not eliminated |
| Public activation from fixture evidence | Operator treats synthetic passes as production qualification | Unsafe live review | Literal denial fields, separate campaign/launch decisions, no public launch CLI | Fresh production evidence and signed launch decision required | Manual misuse outside the supported boundary remains possible |

## Decisions

- Accepted risks with owner and expiry: Joshua Myers explicitly accepts the absence of
  independent human custody/review, plus remote provider receipt and invoice finality
  and host-wide compromise. Joshua must reassess before every production qualification/
  launch window and before raising the USD 5.00 ceiling.
- Required tests and monitoring: existing conformance, campaign, launch-admission,
  revocation, cancellation, ledger, response, and Docker cleanup suites; focused reruns
  for changed boundaries; final `make check`; accountable live self-observation.
- Incident and recovery dependencies: stop future slots on missing/invalid evidence;
  keep uncertain spend held; preserve completion and lifecycle artifacts; use read-only
  inspection; never retry or release automatically; escalate to owner and provider
  billing review for unresolved receipt/cost state.
