# ADR 0005: Do not adopt stock GHP for the GitHub publisher boundary

Date: 2026-09-23. Status: rejected after qualification.

Reviewed candidate: `goodtune/ghp` commit
`338498fc3e60e7c04f428371e20fb6d5ce82c451`. This decision applies to that
revision and does not make a permanent claim about later GHP releases.

## Context

Mos Eisley's planned publisher must accept only an authenticated, typed,
replay-protected publication request. Trusted controller state supplies the
repository, pull request, base SHA and head SHA. The publisher must reject stale
or replayed work, sanitize public text, create one bounded pull-request review and
one check run, and retain an authoritative audit record. Model-facing and
untrusted-code processes must receive neither a credential nor a route to the
publisher or GitHub.

The minimum GitHub App repository permissions for the planned operations are:

| Operation | Fixed REST route | Permission |
|---|---|---|
| Revalidate the PR head/base | `GET /repos/{owner}/{repo}/pulls/{number}` | Pull requests: read |
| Publish a bounded review | `POST /repos/{owner}/{repo}/pulls/{number}/reviews` | Pull requests: write |
| Create a verdict check | `POST /repos/{owner}/{repo}/check-runs` | Checks: write |
| Reconcile or finish that check | `GET` or `PATCH /repos/{owner}/{repo}/check-runs/{id}` | Checks: read/write |

`Pull requests: write` includes more GitHub authority than the single desired
review route, so the broker must enforce the fixed method/path set independently
of the backing App permission. The first release must not accept GraphQL, Git,
release, codeload, issue, repository-administration or arbitrary GitHub API calls.

## Decision

Do not integrate, deploy or recommend the pinned stock GHP revision as Mos
Eisley's production publisher boundary. Keep the publisher capability disabled and
leave local review/evidence workflows unchanged.

Qualification reproduced four blocking mismatches with the required boundary:

1. Agent tokens may be created with no repository list and no permission scopes;
   the resulting token is explicitly open-scoped.
2. Scoped REST requests to unrecognized method/path combinations are forwarded to
   GitHub. Permission categories are also broader than the fixed publisher routes,
   and there is no deployment setting that denies GraphQL.
3. Audit emission returns no result and occurs after forwarding. A failed or
   dropped OpenTelemetry export therefore cannot prevent a GitHub write.
4. The exact dependency/toolchain baseline produced 27 reachable vulnerability
   findings in `govulncheck`, including two in `golang.org/x/crypto` and 25 in the
   Go 1.26.0 standard library.

These are properties of the trusted enforcement layer, not defects that Mos
Eisley's caller-side validation can safely compensate for. A compromised publisher
or stolen GHP administration session could bypass caller-side rules.

The full evidence and source locations are recorded in
[`GHP_QUALIFICATION.md`](../GHP_QUALIFICATION.md). No GitHub App was created, no
credential was provisioned, no service was deployed and no external publication
was attempted.

## Alternatives considered

### Direct short-lived GitHub App token in an isolated publisher

This remains the preferred design candidate. A short-lived CI job or separate
workload identity can mint one installation token after consuming a one-use
publication authorization. GitHub limits the installation to selected repositories
and App permissions; the publisher adds the narrower method/path contract and a
durable local intent/outcome journal. This has a smaller trusted computing base
than GHP plus a second policy proxy.

It is not implemented by this decision. Authenticated one-way IPC, OS/network
isolation, external monotonic replay protection, GitHub App ownership, and the
authoritative audit store still require their own approved design and evidence.

### Stock GHP behind another default-deny proxy

An outer proxy could restrict routes and GraphQL, but it would not make open token
issuance or best-effort post-write audit fail closed. Adding a token-minting wrapper,
route proxy and durable audit transaction around GHP recreates most of a
purpose-built publisher while retaining another privileged stateful service.

### Maintain a Mos Eisley GHP fork

A fork could add mandatory repository/scope policy, constrained machine identity,
exact route allowlists, GraphQL disablement and an acknowledged durable audit
interface. That is a material security-sensitive subsystem rather than a minimal
integration patch. It is not justified before an upstream design is accepted and
independently reviewed.

## Reconsideration gate

Re-open this ADR only for a new exact revision that demonstrates all of the
following in black-box tests:

- empty repository or permission scopes fail at configuration, API and service
  layers;
- a configured repository, App installation, scope and method/path allowlist can
  only narrow access, with unknown routes and GraphQL denied;
- the publisher uses a dedicated constrained machine identity rather than a broad
  interactive administrator session;
- a durable audit intent is acknowledged before forwarding, and unavailable audit
  storage prevents the write;
- revocation is bounded by the required incident objective across all instances;
- source, toolchain, modules, actions and runtime image are immutable and free of
  unresolved blocker/high findings; and
- the exact artifact passes reproducible build, SBOM, license, vulnerability,
  race, integration and adversarial network tests.

## Consequences

The GHP project plan is complete with a no-go outcome at G1. Its G2-G6 deployment,
integration and rollout milestones are intentionally not executed. Mos Eisley still
has no GitHub-write capability, token, network route, publisher command or fallback
PAT path. Roadmap item 8 remains planned under a replacement ADR.
