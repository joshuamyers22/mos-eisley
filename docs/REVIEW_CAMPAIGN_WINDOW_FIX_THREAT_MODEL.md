# Threat Model: review campaign preparation window

## Scope and ownership

- System/version: review-call preparation and fixed three-slot campaign expiry after `bac7dd2`.
- Owner and reviewers: Joshua Myers; accountable human review remains required before another live campaign.
- Date and review trigger: 2026-09-21; a valid third slot received only 13.1 seconds of controller time after a manual ceremony consumed a ten-minute shared window.
- In scope: explicit standard/formal-campaign pre-dispatch review-authorization freshness and campaign-binding enforcement. Out of scope: provider-operation, exchange, controller, guardian, phase-authorization, retry, retention, and spending semantics.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Prepared review authorization | private, dispatch-adjacent | Exact request, price, ledger, expiry, and unique entry must remain bound | Joshua Myers |
| Phase authorization | security-critical | One use, exact scope, maximum 300 seconds | Joshua Myers |
| Spend ledger | financial | Reserve before dispatch; never erase uncertain exposure | Joshua Myers |
| Runtime deadlines | availability/security | Existing operation, exchange, controller, and cleanup caps must not increase | Joshua Myers |

- Actors and capabilities: one operator, trusted host, isolated worker, and OpenAI provider.
- Entry points and trust boundaries: prepared authorization, sealed campaign, explicit phase signature, ledger reservation, credential boundary, and broker exchange.
- Data flows and external dependencies: no data leaves during preparation; dispatch still requires later exact local and signed authorization.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Stale preview is approved later | Attacker retains exact preview | Longer opportunity to request approval | Ordinary calls retain a hard 10-minute cap; only the explicit `formal_campaign` scope receives 30 minutes; pricing expiry may shorten either; exact hash and unused ledger entry remain required | Boundary tests | A sealed formal campaign still has a 20-minute larger window |
| Extended scope is reused for a standalone call or launch | Host selects `formal_campaign` without the fixed campaign ceremony | Unnecessarily stale dispatch-adjacent authorization | The scope is bound into authorization/configuration and the owned probe fails before approval, credentials or reservation unless an exact sealed campaign is supplied; campaign-bound probes reject standard scope | Probe and campaign-dispatch tests | Trusted host code still constructs the inputs |
| Deferred judge scope drifts from the critics | A malformed or tampered envelope/transfer gives the conditional judge a different preparation class | Standard authority can be confused with formal-campaign authority at judge dispatch or during evidence reconstruction | The judge allowance commits scope before reservation; envelope, campaign, probe and retained-transfer checks require exact critic/judge agreement | Envelope/probe/campaign/transfer tamper regressions | Historical expired artifacts remain bound to their original source revision |
| Longer freshness is mistaken for runtime authority | Host conflates expiry with dispatch grant | Unauthorized call | Prepared artifact explicitly grants no dispatch; signed phase authorization and local approval remain mandatory | Existing conformance tests | Trusted-host defects remain possible |
| Runtime call is allowed to run longer | Preparation cap leaks into controller/broker timeouts | Availability or authority overrun | No runtime constants change; focused deadline suites and full gate | Controller/provider tests | None introduced by intended slice |
| Pricing becomes stale | Preparation outlives rates | Incorrect reservation | Authorization expiry remains the minimum of the selected 10- or 30-minute cap and pricing validity | New regression test | Owner must prepare before price expiry |
| Reuse or retry | Longer window permits duplicate issue | Duplicate spend/provider calls | Unique ledger entry and atomic reservation burn approval; no retry API | Existing replay/concurrency tests | Ambiguous calls remain conservatively charged |
| Synthetic formal-campaign phase authority expires under loaded CI | Host scheduling consumes the fixture's deliberately short unit-test certificate before broker setup | Intermittent missing lifecycle evidence obscures product regressions | Formal campaign fixtures request the authority policy's existing 60-second maximum, still clipped by exact phase/controller expiry; expiry-focused unit tests retain the 20-second default; no production limit changes | Campaign-runner, observer-handoff and admission suites plus installed-wheel smoke | A stall beyond the effective clipped scope still fails closed |

## Decisions

- Accepted risks with owner and expiry: Joshua Myers accepts a bounded 20-minute increase only for a sealed formal campaign; reassess before any production launch.
- Required tests and monitoring: exact standard 10-minute and formal 30-minute caps, pricing clipping, unbound-formal rejection, campaign-scope matching including the deferred judge, retained-transfer tamper rejection, expiry rejection, replay prevention, unchanged runtime deadline suites, and the full repository gate.
- Incident and recovery dependencies: a failed sealed campaign remains terminal; rebuild and prepare new artifacts after the corrected commit/image.
