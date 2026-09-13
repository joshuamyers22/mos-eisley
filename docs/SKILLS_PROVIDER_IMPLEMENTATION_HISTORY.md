# Skills and provider implementation history

Archived from project plan §§25.4–25.59 on 2026-09-13 without changing the recorded
bodies. Each entry describes that stage's evidence and limitations; subsequent
entries may supersede its remaining-work statements. This history grants no
runtime authority. Use [plan §25](mos-eisley-plan.md#25-adversarial-review-of-skills-secretref-and-doctor)
for the disposition and [ROADMAP.md](ROADMAP.md) for current delivery status.
Original section numbers and headings are retained for traceability.

### 25.4 Implemented paired evidence gate

Evaluation routes now bind an exact inline or persona-skill prompt asset. A separate
two-arm protocol seals the dataset, full plan, prompt identities, non-inferiority
margins, paired equal-group estimand, fixed stopping rule, and six-comparison family
before results are inspected. The arms must be identical except for their prompt,
and the candidate must be a digest-identified persona skill.

Scoring reverifies the complete dual-authenticated human-grading lineage, averages
repetitions within cases, pairs candidate-minus-baseline case outcomes, then weights
declared independence groups equally. Holdout CLI use consumes an atomic private
claim before validation so failed or repeated attempts cannot be selectively rerun
without explicit local-control tampering. Cost and latency deltas are reported.

This closes the recommended evidence-foundation slice, not persona promotion. Every
artifact denies activation and each report denies promotion. A later milestone must
define independent signed promotion, retained package archives, rollback, expiry,
and drift monitoring before a skill can replace a default.

### 25.5 Implemented independent promotion-readiness gate

An authority policy now enrolls sorted unique Ed25519 release keys and bounds both
its own validity and the maximum lifetime of a decision. The only signable decision
is deterministically derived from the exact sealed comparison plus matching
calibration and holdout reports; both registered gates must pass. The signature
domain binds the authority policy, exact skill and prompt identities, both reports,
and UTC decision window.

Authentication recomputes both reports from their complete dual-human-grade source
chains, rejects authority overlap with any grader or resolver, checks expiry, derives
the decision again, and verifies the signature. A signed failed experiment remains
a denial. The resulting receipt can claim promotion readiness but literally denies
configuration mutation and activation.

This is an evidence-authorization boundary, not installation. The next retained-byte
archive slice is documented below; author signatures, rollback, revocation,
transactional default changes, and drift monitoring remain mandatory future work.

### 25.6 Implemented deterministic package retention

A retained skill archive now serializes every path and exact byte from the loader's
immutable validated snapshot. Canonical base64, per-file byte counts and digests,
canonical path ordering, collision checks, and the existing domain-separated package
digest make the archive deterministic and content addressed. Retention never
reopens the package, so a post-discovery filesystem mutation cannot change the
archive selected by its exact qualified reference.

Archive verification is deliberately semantic as well as structural: it reparses
the retained `SKILL.md` and optional `mos.yaml`, re-applies the prompt-only rules,
and rebuilds the complete descriptor and normalized instruction-body digest from
the retained bytes. It performs no extraction or materialization. Project-source
retention requires invocation-local approval, and the archive schema fixes
installation, activation, and configuration mutation authority to false.

This closes byte retention alone, not deployment. The next subsection adds a current
promotion-evidence binding; authorship, revocation, rollback, transactional
installation/default changes, and post-install drift monitoring remain separate
mandatory gates.

### 25.7 Implemented current archive-to-promotion binding

A `SkillReleaseEvidence` artifact now joins one semantically reverified retained
archive to one authenticated promotion receipt. Creation recomputes both complete
dual-human-grade lineages, the signed promotion decision, and the archive's parsed
descriptor before requiring exact `SkillIdentity` equality. The CLI supplies the
host UTC clock and rejects a receipt at its expiration boundary.

The artifact embeds both sources and commits their canonical digests, exact candidate
identity, check time, and receipt-bounded expiration. It can only represent a passing,
retained evidence state; literal schema fields continue to deny installation,
activation, and configuration mutation. Reverification rebuilds the artifact and can
also require that it remains current at a separately supplied time.

This closes package substitution between evaluated identity and retained bytes. It
does not authenticate the package author, establish an external timestamp, consult a
revocation witness, select a rollback target, materialize files, change defaults, or
monitor post-install drift. Those remain independent prerequisites for deployment.

### 25.8 Implemented authenticated revocation and rollback nomination

A separate release-control policy enrolls sorted unique Ed25519 authorities and
bounds decision lifetime. Every enrolled control identity and public key must be
disjoint from the promotion authorities and all graders and resolvers across both
splits. The only signable control decision is deterministically derived after
reverifying the exact release evidence and its complete upstream lineage.

The signature commits the trust-policy digest, release-evidence digest, current
archive, candidate identity, monotonic sequence, allow/revoke disposition, optional
rollback nomination, and UTC window. A rollback nomination is permitted only for a
revoked release, embeds exact semantically reverified retained bytes in the resulting
receipt, and must identify a different package for the same source-qualified persona
name. It remains a nomination rather than an extraction or install instruction.

A private SQLite anchor is scoped to one release-evidence digest and pins the exact
authority policy, allowed control signers, and a minimum bootstrap sequence. Canonical
entries are hash-linked and fully reverified on every read. Sequence and issue time
must advance, a revocation cannot be removed, and consumers can require the exact
latest signed state. This prevents ordinary older-message replay but not owner-driven
whole-database rollback or cloning; an external monotonic witness is still required.

Every new contract and CLI event continues to fix installation, activation, and
configuration mutation to false. Transactional staging, exact post-write checks,
atomic default switching, crash recovery, and drift-triggered rollback remain the
next independent deployment gate.

### 25.9 Implemented transactional quarantine staging

An exclusive private store can now materialize the exact candidate archive from an
allowed control or the exact embedded rollback archive from a revoked control. The
staging entry point first rebuilds the authenticated control at its recorded time,
then reauthenticates the release, promotion, both comparison splits, and retained
archive at the current host time.

The store policy pins the exact release-control anchor policy and caps both completed
packages and incomplete transactions. Each transaction binds the current control
receipt and exact anchor entry, writes payload files exclusively with private modes,
reconstructs the archive and semantic skill descriptor from the written bytes, writes
the completion manifest last, and fsyncs files and all directory levels. Only then is
the verified directory atomically renamed to its archive-digest path and both sides
of that rename fsynced. Exact existing packages are verified before idempotent reuse;
there is no overwrite or repair path.

Latest-control validation and package commit share one SQLite read transaction. A
concurrent anchor advance cannot commit a newer revocation between verification and
the atomic staging rename. This closes the local check-to-use race, not same-UID
replacement of the entire anchor/store or rollback of their external trust roots.

Interrupted transactions remain bounded and visible under a separate transaction
directory. Status inventories intent/completion-marker presence but never resumes,
deletes, or promotes partial state automatically. Every contract and event continues
to deny installation, activation, and configuration mutation, and no runtime code
reads the quarantine store. Independent signed install authority, atomic default
switching and recovery, and post-install drift evidence remain future gates.

### 25.10 Implemented independent one-use installation authorization

A separate installation-authority policy enrolls sorted unique Ed25519 identities
and keys that must be disjoint from the release controllers, promotion authorities,
graders, and resolvers in both evidence splits. It pins the exact quarantine-store
policy, release-control anchor policy, one private claim-store identity, one inert
installation-target identity, its own validity window, and a maximum decision life.

The derived signable decision reverifies the entire release lineage and every staged
byte. It binds the exact staging manifest, archive, source-qualified persona, candidate
or rollback action, signed control, latest anchor entry, release evidence, claim store,
target, and UTC window. Authentication recomputes that decision, checks the independent
signature, reauthenticates all sources at the host clock, and again requires the same
latest anchor entry. The receipt grants installation permission for only that exact
target while fixing activation and configuration mutation to false; it records that
installation has not occurred.

A private SQLite claim ledger is pinned back to the exact authority policy. Guarded
consumption reverifies the authenticated receipt, burns the signed decision digest
durably before any caller side effect, retains the exact receipt used, and keeps the
release-control read transaction open across the
caller's commit window. Exceptions never refund the claim, so ambiguous or failed
attempts require a newly signed authorization. The raw claim operation is private and
there is deliberately no standalone consume CLI that could waste permission without
an installer transaction.

This is an authority and at-most-once substrate, not deployment. No installed-package
store, default pointer, runtime lookup, completed-install receipt, automatic recovery,
or drift monitor exists. Local claim and control databases can still be rolled back or
cloned by their owner without an external monotonic witness. The next slice must define
the atomic installation/default transaction, complete-or-incomplete recovery evidence,
and post-commit verification before any authorized prompt reaches a model request.

### 25.11 Implemented atomic inert installation and recovery evidence

An installed-store policy now pins one exact installation-authority policy, quarantine
store, at-most-once claim store, and opaque installation-target identity. Its private
layout contains an immutable policy, owner-private cross-process lock, content-addressed
completed packages, and bounded transaction directory. It has no default pointer or
runtime reader.

The installer preflights existing content and capacity before consuming authority,
then reauthenticates the complete evaluation/promotion/release/staging chain under the
latest-control guard. The claim is durably burned before writes. While that revocation
guard remains held, the installed-store lock serializes a second inventory check,
transaction creation, provenance files, exact payload writes, post-write semantic
archive reconstruction, completion-manifest write, directory fsyncs, and atomic rename
to the archive digest. Concurrent installs cannot exceed configured limits or overwrite
an existing exact package. An already installed digest is rejected before consuming a
new authorization when visible at preflight; a later race fails conservatively.

Every completed package retains its exact authenticated authorization, consumed claim,
quarantine manifest, intent, descriptor, and payload. Store loads reverify the external
installation signature and rebuild the full archive from disk. The result alone records
`installation_performed: true`; every store, intent, manifest, result, and event fixes
default mutation, configuration mutation, activation, and runtime lookup to false.

Read-only recovery inspection correlates durable claim-ledger entries with completed
manifests and incomplete intents. It distinguishes `completed`, `incomplete`, and
`claim_only`, and separately inventories transaction directories without an intent.
It never retries, finalizes, deletes, refunds, or changes a default. Local owner rollback
and cloning, same-UID path replacement, external monotonic state, default selection,
runtime consumption, and drift monitoring remain open. The next slice requires a
separate signed default-change authority and an atomic recoverable pointer transaction.

### 25.12 Implemented independent atomic default selection

A default-authority policy now pins independent Ed25519 identities, the exact installed
store and historical installation-authority policy, latest release-control anchor, one
private default-store identity, and a bounded decision lifetime. Default authority IDs
and keys must be disjoint from every evaluator, resolver, promoter, release controller,
and installer in the reverified source lineage.

Each decision binds the exact installed manifest, historical installation authorization
and signed installation decision, archive and persona identity, current release-control
entry, candidate or rollback action, next sequence, expected previous pointer digest,
and validity window. Authentication rebuilds the complete evaluation through installed
package provenance and rejects any release-control or default-state advance.

The private default store uses rollback-journal SQLite with `synchronous=EXTRA`. Under
the latest release-control read guard, one `BEGIN IMMEDIATE` transaction reverifies the
entire canonical revision chain and installed packages, performs the signed
sequence/prior-pointer compare-and-swap, inserts the unique decision and immutable
selection record, and updates the singleton current pointer. Consumption and mutation
therefore either commit together or both roll back. An ambiguous commit response is
resolved through read-only status; automatic recovery is unnecessary and absent.

This is a narrow control-plane configuration change. Results record
`default_changed: true`, while every authority, pointer, result, status, and event denies
all other configuration mutation, activation, and runtime lookup. No shipped runtime
reads the pointer. Local database/control rollback or cloning, external monotonic state,
post-selection health evidence, runtime consumption, drift monitoring, and automatic
rollback remain open. The next slice adds post-promotion drift and health evidence
before any selected prompt can reach a model request.

### 25.13 Implemented signed post-selection health and drift eligibility

A health-authority policy now pins the exact default/control/promotion trust roots and
requires at least two independent Ed25519 identities. The identities and keys must be
disjoint from each other by role and from every evaluator, resolver, promoter, release
controller, installer, and default selector in the fully reverified source lineage.

One signer fixes the exact current pointer, installed bytes, latest release-control
entry, authenticated promotion holdout reference, measurement-protocol digest,
freshness/lifetime limits, independent-group floor, and direction-aware numeric
thresholds. A distinct observer signs the exact post-selection measurement window,
evidence-bundle digest, group counts, confidence-bound rates in integer parts per
million, complete-cost coverage and delta, and p95 latency delta.

Issuance rebuilds promotion and release control, holds the latest local control guard,
verifies the complete default revision chain and installed package, and accepts only
the archive currently permitted by control. It rejects observations that predate
selection, are future-dated or stale, have insufficient groups, fail the original
registered health gate, or drift beyond the separately signed tolerances from the
holdout report. The result expires at the earliest source or policy boundary.

This remains evidence, not execution. The CLI accepts no private keys; the evidence
bundle and measurement protocol are authenticated by digest but not fetched or
recomputed. Local database rollback/cloning, clock integrity, continuous monitoring,
alert delivery, provider dispatch, and automatic rollback remain
open. Every artifact denies dispatch, activation, configuration mutation, and
automatic rollback. The non-sending preparation substrate below addresses one-use
request, prompt, health, route, and spending admission; brokered provider dispatch
remains a separate gate.

### 25.14 Implemented one-use skill runtime preparation and spend admission

A new runtime-authority policy pins the exact health authority, default store, model
registry, and shared spend ledger while requiring its signers to be identity- and
key-disjoint from every upstream health, default, installation, release, promotion,
grading, and resolution authority. The signable decision fixes one request, current
pointer and health receipt, exact reconstructed persona prompt, provider/model/effort
route, routing-preflight digest, normalized provider/broker request hashes, reviewed
spend policy, deterministic ledger entry, worst-case reservation, and short validity
window.

Preparation reverifies the full skill-health chain, selected installed bytes, current
control/default state, registry and exact route with no effort substitution. The
request explicitly acknowledges external data transfer but no transfer occurs. To
avoid a non-atomic claim-ledger/spend-ledger composition, the shared spend-ledger insert
itself is the one-use authorization burn. Verified release-control and default-pointer
read locks remain held across that insertion. All provider-independent checks occur
first. The reservation pessimistically charges the policy's maximum input tokens plus
the requested output cap without contacting a provider.

The prepared private artifact contains the exact prompt and user input but issues no
bearer grant and records that no request was sent. A read-only status path distinguishes
absent, held, settled, uncertain, and violation states while denying retry and automatic
budget release. Failed inserts consume nothing; a crash after commit leaves authority
burned and budget held.

This is not dispatch. The routing preflight is exact-route matched and bound by the
independent runtime signature. Runtime policy schema version 2 and the preparation path
now also pin and recompute its complete empirical source chain. The existing provider
transport cannot consume a pre-reserved entry and must not be composed because it would
reserve twice. External monotonic state, dispatch authority, credentials, network send,
response audit, settlement, and automatic rollback remain open.

### 25.15 Implemented full routing revalidation and guarded broker admission

A pre-created admission-store policy pins one private store identity, both control
anchors, the default store, and the spend ledger. The signed runtime-authority policy
pins that complete policy, plus the routing activation-authority and control-anchor
policies. Runtime signers must be independent of authorities and evaluators in both the
skill and routing lineages.

Preparation and broker admission now reconstruct the routing preflight from its full
calibration, holdout, promotion, operational-signature, eligibility, and anchored
control sources. The admission commit holds read locks on the exact latest routing
control, exact latest skill release control, current default pointer, and exact held
spend entry. A deterministic insert uniquely claims the prepared request, runtime
decision, and existing ledger entry in the pinned admission store. It does not create
a second reservation, and injected failures roll back only the admission while leaving
the earlier conservative reservation held.

Admission remains non-executing. It contains no request body, credential, or bearer
capability, and every policy, artifact, status, and event denies provider dispatch,
send, retry, and automatic release. Store copying/rollback, clock integrity, and
organizational collusion remain external. The following slice adds independent
dispatch authority and durable consumption while deliberately deferring the first
request-bound bearer, provider transfer, and ambiguous-send settlement.

### 25.16 Implemented independent dispatch-authority consumption

A separate Ed25519 dispatch policy now pins the runtime-preparation authority and a
pre-created claim-store policy. That store policy pins the admission store, both
control anchors, default store, and spend ledger. Dispatch signers must be identity-
and key-disjoint from runtime-preparation signers. Decisions last at most 60 seconds
and bind the exact admission, prepared and signed runtime artifacts, route, normalized
provider and broker request hashes, both controls, default pointer, ledger entry, and
reservation.

Consumption reconstructs the complete routing and skill lineages and exact stored
admission. Read guards hold both latest controls, current default, existing held spend,
and exact admission through an at-most-once claim commit. Replay, stale state, policy
substitution, settled spend, expiry, and invalid signatures fail closed. Injected
database failure leaves the admission and conservative spend reservation unchanged.

The resulting claim authorizes only a future exchange for one request-bound grant. It
is not a bearer and no current transport accepts it. Every contract and event records
that no grant was issued, direct provider dispatch is unauthorized, no request was
sent, and retry and automatic budget release are denied. Ephemeral bearer issuance,
the durable before-send boundary, pre-reserved transport, outcome settlement, external
monotonic state, and credentialed conformance remain open.

### 25.17 Implemented ephemeral request-bound broker capability

Dispatch-authority policy schema version 2 now pins a pre-created broker-grant-store
policy, which in turn pins the dispatch-claim and admission stores, both control
anchors, default store, and spend ledger. Grant issuance reconstructs the entire
routing and skill evidence graph, exact signed preparation and admission, and exact
signed and consumed dispatch authority. It holds both control anchors, current
default, existing held spend, admission, and dispatch claim through one durable unique
issuance commit.

The issuance store persists only exact provenance and a domain-separated hash of a
fresh random 256-bit capability. The bearer remains in process memory, is capped at 30
seconds and by the signed decision, redacts its representation, can be delivered once,
and can be validly redeemed once under a lock. Redemption returns only issuance
metadata, never prompt bytes, credentials, or a transport. A committed but lost bearer
cannot be recreated, and an injected store failure returns no bearer while leaving all
prior state and spend unchanged.

No CLI path exports the secret. CLI commands create and inspect only the hash-bearing
durable store. Provider request transmission, pre-reserved settlement, an fsynced
before-send marker, response handling, cancellation, timeout, crash recovery, and
credentialed conformance remain open. Missing or ambiguous outcomes must never imply
retry or budget release.

### 25.18 Implemented provider-owning pre-reserved transaction

Broker-grant-store policy schema version 2 now pins one provider-transaction-store
policy. The latter pins the grant-store identity, both control anchors, default store,
spend ledger, capacity, and a maximum 60-second provider wait. Before redemption, the
transaction checks exact preparation/issuance request hashes, route, model, pricing,
and existing reservation plus a zero-retry OpenAI transport contract.

Fresh routing-control, skill-control, default, held-spend, and exact-grant read guards
remain open while the capability is burned and an exact send intent commits in a
private rollback-journal SQLite store using `synchronous=EXTRA`. Transport is invoked
only after that commit and at most once. The store persists no bearer, prompt,
credential, request body, or response body.

Verified model/tier/usage settles the existing ledger entry at locally computed actual
cost. Provider errors, malformed or missing usage, timeout, cancellation, and lost
response retain the full reservation as uncertain. Pricing-bound violations retain
the full reservation as a blocking violation. The ledger commits before hash-only
outcome metadata, so either cross-store failure remains conservatively accounted
behind the durable marker. Recovery never authorizes retry or automatic release.

Credentialed conformance and external billing reconciliation remain open. Durable
content-verified response/result publication is the separately pinned next layer.

### 25.19 Implemented content-verified runtime response publication

Provider-transaction policy schema version 2 now pins one complete response-store
policy. That policy binds the exact transaction-store identity, capacity, individual
and aggregate byte limits while structurally denying reasoning or provider-credential
publication, provider retry, and automatic budget release.

Publication accepts only the exact stored `response_received` transaction with its
existing ledger entry settled. It recomputes response bytes, request and response
digests, full preparation/issuance/route/ledger lineage, model, provider request ID,
stop reason, token usage, and locally charged cost. The exact canonical provider
response, reasoning-free result, manifest, send intent, and outcome commit together in
one private rollback-journal SQLite transaction. Unique identities reject replay.

Every subsequent status or result read repeats canonical-record, digest, lineage, and
result-to-raw-response verification. The public result accepts only assistant text;
reasoning, including encrypted provider state, remains retained in the private raw
record. Tool-bearing and reasoning-only responses are not publishable. The CLI can
create and inspect the store and read verified results but has no raw-response export.
Provider credentials are not accepted or added, but model-authored text remains
untrusted and may require a separate sensitive-output policy.

This closes local durable result publication, not external proof. Same-UID access,
trusted transport/parser behavior, store rollback/cloning, retention policy, hardware
durability, provider authorship, invoice reconciliation, and credentialed OpenAI
conformance remain open. A separately authorized credentialed run must traverse this
exact zero-retry boundary before stronger operational claims are made.

### 25.20 Implemented authenticated runtime conformance attestation

A separate conformance policy now pins the exact response-store policy, UTC validity
and freshness bounds, canonical trusted Ed25519 observer identities and keys, reviewed
OpenAI SDK versions, production origin, Responses API family, API-key credential mode,
official SDK, zero-retry, no-storage, and no-truncation requirements.

After an operator actually observes a credentialed exchange, signable metadata binds
the exact verified publication, result, transaction, model, effort, provider request
ID, SDK version, and a digest of separately retained redacted transport evidence. The
derive CLI requires explicit credentialed-exchange acknowledgement and never accepts a
provider credential or signing key. External signing retains private-key custody.

Authentication verifies the enrolled observer's domain-separated Ed25519 signature,
policy and observation freshness, allowlisted SDK, and the exact private publication.
Loading that publication repeats canonical raw-response, result, settled transaction,
and ledger-lineage verification. Output carries hashes and metadata only, not prompt,
answer, reasoning, raw response, API credential, or signing key.

This authenticates an observer claim, not the truth of every claimed transport fact.
Provider authorship, TLS peer identity, invoice reconciliation, quality, promotion,
and routing activation remain structurally false. The observer can lie or collude;
the external evidence digest is not fetched. No live or paid request was made for this
milestone. Next, a separately authorized run must traverse the exact path, followed by
external billing/provider-receipt reconciliation and the repeated blinded quality
study before stronger operational or routing claims.

### 25.21 Implemented portable publication-history witness

Response-store policy schema version 2 now persists and validates an explicit,
gap-free publication sequence rather than SQLite's mutable implicit row ID. The store
computes a domain-separated rolling SHA-256 commitment over publication-manifest
digests in that order only after fully reverifying every canonical raw response,
result, manifest, transaction, and ledger relationship. The hash-only
history includes store-policy identity, count, rolling digest, and latest publication
identifiers, never raw response or published assistant content.

A separate witness policy pins that exact store, UTC validity and freshness bounds,
positive minimum publication count, and canonical trusted Ed25519 witness identities
and keys. Signable checkpoints bind the policy, full current history, and witness time.
Verification authenticates the signature and requires that checkpoint history remain
an exact prefix of the current store. Legitimate later publications remain valid;
deletion, reordering, or divergence at or before the checkpoint fails closed.

The CLI derives and verifies hash-only artifacts but never accepts signing private
keys. A useful signed checkpoint must be retained in a separate trust or storage
domain. Both checkpoint and verification schemas explicitly deny proof of external
retention or newest-checkpoint delivery, as well as response/result export, retry, and
budget release. A matching old store and old checkpoint can still be presented if a
newer external checkpoint is suppressed. External delivery, latest-state service,
clock integrity, key custody, and availability remain open, as do provider billing
reconciliation and separately authorized credentialed conformance.

### 25.22 Implemented authenticated aggregate billing evidence

A billing policy now pins the exact response-store and conformance policies, UTC
validity and freshness bounds, the documented OpenAI organization completion-usage and
cost endpoints, their narrowest supported bucket widths and grouping dimensions, and
canonical trusted Ed25519 billing auditors. Billing identities and keys must be
disjoint from every enrolled conformance observer at authentication time.

Signable evidence reauthenticates the full historical conformance receipt and private
publication before binding transaction, outcome, ledger, provider response identifier,
route, local usage and cost, exactly matching external aggregate values, closed bucket
windows, hashes of project/API-key identifiers, and digests of separately retained
complete Admin API pages. The attested scope must contain exactly one request. Evidence
retrieval must follow both the one-minute usage bucket and one-day cost bucket.

The documented aggregates do not expose a response ID, and Mos Eisley does not fetch or
parse the retained evidence in this layer. Consequently every artifact fixes exact
request-cost attribution, provider authorship, and invoice finality to false even when
the exclusive aggregate matches exactly. Ledger mutation, automatic budget release,
retry, quality, promotion, and routing activation are also structurally denied. The CLI
only derives and authenticates metadata, never accepts provider credentials or signing
private keys, and does not export content or raw billing pages.

No live or paid request was made for this milestone. Next, separately authorized
credentialed conformance and a credential-isolated strict Admin API evidence collector
must exercise the real boundary. Request-level claims require a future documented
provider field rather than inference from aggregate isolation.

### 25.23 Implemented credential-isolated Admin API billing collection

An explicit-consent `openai-billing-collect` process now owns `OPENAI_ADMIN_KEY` only
for bounded OpenAI organization completion-usage and cost reads. It first
reauthenticates the exact conformance publication and current billing policy, rejects
open reporting windows and unusable output paths before credential access, then uses
the official SDK with automatic retries, environment proxies, redirects, and streaming
disabled. Each decoded response and the complete cursor chain are bounded.

The retained private bundle strictly validates one exact one-minute completion group,
project/API-key/model/default-tier equality, one model request, one closed daily cost
bucket, exact project/API-key cost groups, no duplicate line items, and an integer
microusd total. Canonical rolling digests over the retained raw pages feed the existing
signable observation path; the collector neither holds a signing key nor mutates the
spend ledger. Console output omits raw pages, identifiers, totals, prompts, responses,
and the Admin credential.

The adversarial boundary is narrower than “exclusive request receipt.” The completion
endpoint proves only one request in the selected minute, while the costs endpoint is a
daily aggregate with no response ID. Collection therefore fixes complete daily
API-key exclusivity and exact request-cost attribution to false. The existing derive
step still requires a separate completeness/exclusivity attestation, and authenticated
evidence continues to deny invoice finality, ledger release, retry, quality, promotion,
and activation. Fixture HTTP tests exercise the SDK boundary without a paid model
request. A separately authorized real conformance run and real Admin read remain
operator work.

### 25.24 Implemented failure-preserving brokered evaluation assembly

Broker audit outcome schema version 3 now requires bounded elapsed latency for every
terminal state and distinguishes a generic provider execution error, an actual broker
deadline, and caller cancellation. Successful outcomes continue to bind exact reply
bytes. Failed and cancelled outcomes carry no response hash or provider request ID;
their recovery state preserves absent, held, uncertain, or violation ledger exposure
without authorizing retry or release. Older outcomes remain readable for recovery but
cannot mint failure evidence without the new latency and error fields.

A verification-only failure compiler requires an independently supplied assignment
authorization, the exact private audit chain, and the named shared ledger. It emits no
invented response, usage, critique, or cost when no reservation exists. A separate
assembler revalidates every artifact against the blinded execution batch, requires
exact sample coverage and unique authorization, outcome, response, provider-request,
and ledger identities, and restores canonical batch order. Omission, duplication,
route substitution, and mixed-ledger assembly fail closed.

The assembled `BrokeredEvaluationResultSet` is intentionally not `RawResultSet`. Its
contract and CLI output fix credentialed conformance proof, live-result issuance,
grading, scoring, promotion, retry, and automatic budget release to false. This closes
failure-preserving coverage composition only. A real provider conformance run,
authenticated live-execution policy, and separately reviewed conversion remain
mandatory before empirical scoring. No provider or paid request was made.

### 25.25 Implemented authenticated brokered evaluation conformance receipt

A pre-registered evaluation-conformance policy now fixes one exact blinded OpenAI
assignment before an observer claim can be accepted: plan, batch, sample, candidate,
evaluation request, serialized provider request, spend policy, ledger, ledger entry,
UTC window, observation age, SDK allowlist, and sorted unique Ed25519 observer keys.
Provider, endpoint, Responses family, API-key mode, explicit conformance command,
official SDK, bounded client, isolated broker, zero retries, disabled storage, and
disabled truncation are strict literals rather than signable free text.

Derivation requires explicit credentialed-exchange attestation plus the successful
broker artifact, exact blinded batch, independently retained assignment authorization,
private audit, and shared ledger. Authentication verifies the domain-separated
signature and freshness, then reparses every contract and reopens the audit and ledger.
The terminal response and outcome hashes, measured latency, settled status, and
charged amount must continue to match. Trust anchors or derived inputs inside the
audit tree, symlink aliases, hard links to the audit authorization, and output/input
overlap fail closed. CLI output omits prompt, critique, usage, provider request ID,
raw response, credential, and signing key.

This authenticates a trusted observer statement, not OpenAI authorship or billing.
The observer can lie; transport-evidence bytes are externally retained and not fetched;
the observation time and host clock are trusted. Only successful settled token-usage
artifacts qualify because current failure state does not prove whether a provider send
occurred. One probe cannot establish complete-batch conformance and every policy,
observation, receipt, and event fixes conversion, grading, scoring, quality, promotion,
and routing activation to false. A separately authorized real probe is still required;
tests use synthetic artifacts and keys and make no provider or paid request.

### 25.26 Implemented no-send evaluation conformance ceremony preflight

A dedicated preparation command now deterministically derives the exact
evaluation-conformance policy from one blinded assignment, reviewed spend policy,
existing shared ledger, planned fresh audit path, UTC window, sorted observer roster,
and sorted installed-SDK allowlist. It reconstructs the strict OpenAI request and
pins its hash plus every assignment and spending identity. The ceremony reads no
provider credential, creates no audit, makes no reservation, starts no container,
and sends no request; its event reports those facts explicitly.

The paid-capable `openai-conformance` command now requires that prepared policy.
Before reading `OPENAI_API_KEY`, it reconstructs the authorization and rejects any
request, assignment, spend-policy, ledger, audit-derived entry, installed SDK, or
validity mismatch. The policy window must fit inside the spend-policy window and
cover the configured request timeout. Both preparation and live preflight require an
unblocked ledger, unused exact entry, fresh audit path, and non-overlapping inputs and
outputs. Atomic spending admission remains authoritative against concurrent changes.

This is a local pre-credential commitment, not a spend reservation, provider
authorization, conformance result, or observer signature. File custody, host clocks,
same-UID races, and ledger rollback/cloning remain outside the local proof. All
conversion, grading, scoring, promotion, and routing flags remain false. Tests use
synthetic provider and Docker behavior and make no credentialed or paid request.

### 25.27 Implemented signed evaluation conformance authorization

The paid-capable evaluation conformance boundary now requires an independent,
short-lived Ed25519 authorization in addition to explicit local transfer confirmation.
A strict authority policy enrolls sorted unique identities and keys and caps each
authorization at one hour. Every enrolled authority must be disjoint by both identity
and key from every post-run observer in the exact conformance policy.

Unsigned derivation binds the authority and conformance policy hashes, complete
assignment and provider-request identity, spend policy, ledger and entry, maximum
micro-USD exposure, issue time, and expiry. It reads no provider credential or private
key, reserves no money, creates no audit, and sends nothing. Signing is out of process
under a distinct domain. Before API-key access, the live command verifies enrollment,
signature, exact reconstructed content, authority separation, nested authority,
conformance and spend windows, and enough signed lifetime for the request timeout.

The signature authorizes one exact blinded transfer, credential access, and bounded
spend; it explicitly denies unblinded transfer, retry, automatic budget release,
conversion, grading, scoring, promotion, and routing activation. It proves possession
of an enrolled key, not human identity or informed judgment. Trust-policy custody,
signer independence, clocks, same-UID replacement, and ledger rollback/cloning remain
external. Tests use synthetic keys and transport behavior and make no credentialed or
paid request.

### 25.28 Recorded first authenticated Terra/medium live conformance success

The first committed Terra/medium campaign probe traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled the shared campaign ledger at 3,468 micro-USD, and
published a strict artifact with 384 input tokens, 225 combined visible/reasoning
output tokens, and 6,642 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and freshness
lineage.

This is one qualifying Terra/medium success under the frozen live-conformance gate.
Together with the earlier Luna/low result, progress is 2 of 18 required successes:
Luna/low and Terra/medium are each 1 of 3. The unused expired no-send authorization
package did not access a credential, create an audit, reserve spend, or contact the
provider and does not count as a live attempt.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key custody,
and retained evidence remain trusted. Four probes remain in the initial campaign,
followed by 12 newly precommitted successes and the five frozen failure boundaries.
No calibration conversion is authorized.

### 25.29 Recorded first authenticated Sol/medium live conformance success

The committed Sol/medium campaign probe traversed the exact independently signed,
explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 8,448 micro-USD against the shared campaign ledger,
and published a strict artifact with 377 input tokens, 347 combined
visible/reasoning output tokens, and 9,300 ms measured latency. A separately enrolled
observer signed the derived record, and local authentication reverified the exact
batch, request, authorization, policy, artifact, audit, ledger entry, response hash,
SDK, and freshness lineage.

This is one qualifying Sol/medium success under the frozen live-conformance gate.
Together with the earlier Luna/low and Terra/medium results, progress is 3 of 18:
each of those profiles is 1 of 3. The shared success ledger contains two settled
campaign entries, 11,916 micro-USD charged in total, no unresolved entries, and
138,084 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key
custody, and retained evidence remain trusted. Three probes remain in the initial
campaign, followed by 12 newly precommitted successes and the five frozen failure
boundaries. No calibration conversion is authorized.

### 25.30 Recorded first authenticated Sol/high live conformance success

The committed Sol/high campaign probe traversed the exact independently signed,
explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 3,008 micro-USD against the shared campaign ledger,
and published a strict artifact with 392 input tokens, 72 combined visible/reasoning
output tokens, and 5,625 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is one qualifying Sol/high success under the frozen live-conformance gate.
Together with the Luna/low, Terra/medium, and Sol/medium results, progress is 4 of 18:
each of those profiles is 1 of 3. The shared success ledger contains three settled
campaign entries, 14,924 micro-USD charged in total, no unresolved entries, and
135,076 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key
custody, and retained evidence remain trusted. Two probes remain in the initial
campaign, followed by 12 newly precommitted successes and the five frozen failure
boundaries. No calibration conversion is authorized.

### 25.31 Recorded first authenticated Astra/high live conformance success

The committed Astra/high campaign probe traversed the exact independently signed,
explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 18,050 micro-USD against the shared campaign ledger,
and published a strict artifact with 390 input tokens, 283 combined
visible/reasoning output tokens, and 9,569 ms measured latency. A separately enrolled
observer signed the derived record, and local authentication reverified the exact
batch, request, authorization, policy, artifact, audit, ledger entry, response hash,
SDK, and freshness lineage.

This is one qualifying Astra/high success under the frozen live-conformance gate.
Together with the Luna/low, Terra/medium, Sol/medium, and Sol/high results, progress
is 5 of 18: each of those profiles is 1 of 3. The shared success ledger contains four
settled campaign entries, 32,974 micro-USD charged in total, no unresolved entries,
and 117,026 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key
custody, and retained evidence remain trusted. One Astra/max probe remains in the
initial campaign, followed by 12 newly precommitted successes and the five frozen
failure boundaries. No calibration conversion is authorized.

### 25.32 Recorded first authenticated Astra/max live conformance success

The committed Astra/max campaign probe traversed the exact independently signed,
explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 12,450 micro-USD against the shared campaign ledger,
and published a strict artifact with 385 input tokens, 172 combined
visible/reasoning output tokens, and 8,143 ms measured latency. A separately enrolled
observer signed the derived record, and local authentication reverified the exact
batch, request, authorization, policy, artifact, audit, ledger entry, response hash,
SDK, and freshness lineage.

This is one qualifying Astra/max success under the frozen live-conformance gate.
Together with the Luna/low, Terra/medium, Sol/medium, Sol/high, and Astra/high
results, progress is 6 of 18: every profile is now 1 of 3. The initial sealed
five-probe campaign is complete. Its shared success ledger contains five settled
entries, 45,424 micro-USD charged in total, no unresolved entries, and 104,576
micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key
custody, and retained evidence remain trusted. Twelve newly precommitted successful
probes and the five frozen failure boundaries remain. No calibration conversion is
authorized.

### 25.33 Sealed the second OpenAI live-conformance campaign

A second private campaign manifest now commits the 12 remaining success-matrix
attempts before any of their provider outcomes are known: two distinct assignments
for each of Luna/low, Terra/medium, Sol/medium, Sol/high, Astra/high, and Astra/max.
Selection is mechanical—the two lexicographically smallest sample IDs for each exact
profile that are absent from the six authenticated prior-success receipts. The
manifest binds those receipts, the existing blinded batch and plan, the exact route,
execution sequence, standard pricing source and rates, token caps, and a fresh shared
ledger. It also requires the campaign to stop after any non-success.

The private manifest digest is
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8`.
Its fresh ledger identity is
`3a70da17b19c50af40722f1746e3ab9b0a0eb5ce32851a89029cfe9a656bfae7`,
with a 300,000 micro-USD ceiling. Two capped attempts per profile produce a 217,278
micro-USD worst case and 82,722 micro-USD headroom. At sealing, the ledger contained
zero entries, zero charged exposure, and no unresolved or blocking state.

The sealing path read no credential, made no provider request, reserved no spend,
and authorized no data transfer, conformance, retry, grading, scoring, promotion, or
routing activation. The committed attempts are not presumed successes: every outcome
must remain in chronology, and any failure requires a reviewed disposition and a new
commitment under the frozen gate rules. Fresh per-attempt policies, independent
signature, and explicit local consent remain mandatory.

### 25.34 Recorded second authenticated Luna/low live conformance success

The first committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 335 micro-USD against the campaign ledger, and
published a strict artifact with 377 input tokens, 216 combined visible/reasoning
output tokens, and 13,302 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is the second qualifying Luna/low success under the frozen live-conformance
gate and the first completed attempt from the second campaign. Overall progress is 7
of 18: Luna/low is 2 of 3 and Terra/medium, Sol/medium, Sol/high, Astra/high, and
Astra/max are each 1 of 3. The second campaign ledger contains one settled entry,
335 micro-USD charged, no unresolved entries, and 299,665 micro-USD available.

After the provider request had completed, the operator exposed the credential in an
interactive shell input. The credential was treated as compromised and revoked
before campaign continuation; a repository scan found no persisted project copy.
This post-run handling incident does not alter the retained request lineage, but it
requires a new credential for every later live attempt and remains an operator- and
shell-history boundary rather than machine-verifiable proof of revocation.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion,
and routing activation to false. Eleven precommitted successful probes and the five
frozen failure boundaries remain. No calibration conversion is authorized.

### 25.35 Completed the Luna/low live-conformance profile

The second committed attempt in the second campaign traversed the exact
independently signed, explicit-consent, zero-retry broker path on 2026-09-08. The
broker retained a response-received audit, settled 314 micro-USD against the campaign
ledger, and published a strict artifact with 386 input tokens, 197 combined
visible/reasoning output tokens, and 6,254 ms measured latency. A separately enrolled
observer signed the derived record, and local authentication reverified the exact
batch, request, authorization, policy, artifact, audit, ledger entry, response hash,
SDK, and freshness lineage.

This is the third qualifying Luna/low success under the frozen live-conformance gate
and completes that exact profile at 3 of 3 consecutive authenticated successes.
Overall progress is 8 of 18: Terra/medium, Sol/medium, Sol/high, Astra/high, and
Astra/max remain 1 of 3. The second campaign ledger contains two settled entries,
649 micro-USD charged, no unresolved entries, and 299,351 micro-USD available.

Profile completion is not gate completion. The authenticated receipt continues to
fix provider authorship, billing reconciliation, complete-batch conformance, grading,
scoring, quality, promotion, and routing activation to false. Ten precommitted
successful probes and the five frozen failure boundaries remain. No calibration
conversion is authorized.

### 25.36 Recorded second authenticated Terra/medium live conformance success

The third committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 2,590 micro-USD against the campaign ledger, and
published a strict artifact with 377 input tokens, 153 output tokens, and 5,024 ms
measured latency. The provider usage record reported zero reasoning tokens; that is
retained as usage data rather than interpreted as proof about provider-internal
reasoning. A separately enrolled observer signed the derived record, and local
authentication reverified the exact batch, request, authorization, policy, artifact,
audit, ledger entry, response hash, SDK, and freshness lineage.

This is the second qualifying Terra/medium success under the frozen live-conformance
gate. Overall progress is 9 of 18: Luna/low is complete at 3 of 3, Terra/medium is 2
of 3, and Sol/medium, Sol/high, Astra/high, and Astra/max are each 1 of 3. The second
campaign ledger contains three settled entries, 3,239 micro-USD charged, no unresolved
entries, and 296,761 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. Nine precommitted successful probes and the five frozen
failure boundaries remain. No calibration conversion is authorized.

### 25.37 Completed the Terra/medium live-conformance profile

The fourth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 6,766 micro-USD against the campaign ledger, and
published a strict artifact with 425 input tokens, 493 combined visible/reasoning
output tokens, and 9,419 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is the third qualifying Terra/medium success under the frozen live-conformance
gate and completes that exact profile at 3 of 3 consecutive authenticated successes.
Overall progress is 10 of 18: Luna/low and Terra/medium are complete, while
Sol/medium, Sol/high, Astra/high, and Astra/max are each 1 of 3. The second campaign
ledger contains four settled entries, 10,005 micro-USD charged, no unresolved
entries, and 289,995 micro-USD available.

Profile completion is not gate completion. The authenticated receipt continues to
fix provider authorship, billing reconciliation, complete-batch conformance, grading,
scoring, quality, promotion, and routing activation to false. Eight precommitted
successful probes and the five frozen failure boundaries remain. No calibration
conversion is authorized.

### 25.38 Recorded second authenticated Sol/medium live conformance success

The fifth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 4,712 micro-USD against the campaign ledger, and
published a strict artifact with 393 input tokens, 157 combined visible/reasoning
output tokens, and 6,887 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

An earlier no-send preparation for the same committed sequence expired before
signature, credential access, reservation, or provider contact. It remains retained
privately under an explicit archival name. Regeneration preserved the exact committed
sample, request, ledger entry, model, effort, token caps, and maximum while creating
fresh policy and authorization windows; it did not create or conceal a live provider
outcome.

This is the second qualifying Sol/medium success under the frozen live-conformance
gate. Overall progress is 11 of 18: Luna/low and Terra/medium are complete at 3 of 3,
Sol/medium is 2 of 3, and Sol/high, Astra/high, and Astra/max are each 1 of 3. The
second campaign ledger contains five settled entries, 14,717 micro-USD charged, no
unresolved entries, and 285,283 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. Seven precommitted successful probes and the five frozen
failure boundaries remain. No calibration conversion is authorized.

### 25.39 Completed the Sol/medium live-conformance profile

The sixth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 4,608 micro-USD against the campaign ledger, and
published a strict artifact with 377 input tokens, 155 combined visible/reasoning
output tokens, and 5,565 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is the third qualifying Sol/medium success under the frozen live-conformance
gate and completes that exact profile at 3 of 3 consecutive authenticated successes.
Overall progress is 12 of 18: Luna/low, Terra/medium, and Sol/medium are complete,
while Sol/high, Astra/high, and Astra/max are each 1 of 3. The second campaign ledger
contains six settled entries, 19,325 micro-USD charged, no unresolved entries, and
280,675 micro-USD available.

Profile completion is not gate completion. The authenticated receipt continues to
fix provider authorship, billing reconciliation, complete-batch conformance, grading,
scoring, quality, promotion, and routing activation to false. Six precommitted
successful probes and the five frozen failure boundaries remain. No calibration
conversion is authorized.

### 25.40 Recorded second authenticated Sol/high live conformance success

The seventh committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 4,788 micro-USD against the campaign ledger, and
published a strict artifact with 397 input tokens, 160 combined visible/reasoning
output tokens, and 5,736 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is the second qualifying Sol/high success under the frozen live-conformance
gate. Overall progress is 13 of 18: Luna/low, Terra/medium, and Sol/medium are
complete at 3 of 3, Sol/high is 2 of 3, and Astra/high and Astra/max are each 1 of 3.
The second campaign ledger contains seven settled entries, 24,113 micro-USD charged,
no unresolved entries, and 275,887 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. Five precommitted successful probes and the five frozen
failure boundaries remain. No calibration conversion is authorized.

### 25.41 Completed the Sol/high live-conformance profile

The eighth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 3,776 micro-USD against the campaign ledger, and
published a strict artifact with 399 input tokens, 109 combined visible/reasoning
output tokens, including 84 reported reasoning tokens, and 5,334 ms measured latency.
A separately enrolled observer signed the derived record, and local authentication
reverified the exact batch, request, authorization, policy, artifact, audit, ledger
entry, response hash, SDK, and freshness lineage.

This is the third qualifying Sol/high success under the frozen live-conformance gate
and completes that exact profile at 3 of 3 consecutive authenticated successes.
Overall progress is 14 of 18: Luna/low, Terra/medium, Sol/medium, and Sol/high are
complete, while Astra/high and Astra/max are each 1 of 3. The second campaign ledger
contains eight settled entries, 27,889 micro-USD charged, no unresolved entries, and
272,111 micro-USD available.

Profile completion is not gate completion. The authenticated receipt continues to
fix provider authorship, billing reconciliation, complete-batch conformance, grading,
scoring, quality, promotion, and routing activation to false. Four precommitted
successful probes and the five frozen failure boundaries remain. No calibration
conversion is authorized.

### 25.42 Recorded second authenticated Astra/high live conformance success

The ninth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 25,700 micro-USD against the campaign ledger, and
published a strict artifact with 375 input tokens, 439 combined visible/reasoning
output tokens, including 285 reported reasoning tokens, and 13,846 ms measured
latency. A separately enrolled observer signed the derived record, and local
authentication reverified the exact batch, request, authorization, policy, artifact,
audit, ledger entry, response hash, SDK, and freshness lineage.

This is the second qualifying Astra/high success under the frozen live-conformance
gate. Overall progress is 15 of 18: Luna/low, Terra/medium, Sol/medium, and Sol/high
are complete at 3 of 3, Astra/high is 2 of 3, and Astra/max is 1 of 3. The second
campaign ledger contains nine settled entries, 53,589 micro-USD charged, no
unresolved entries, and 246,411 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion,
and routing activation to false. Three precommitted successful probes and the five
frozen failure boundaries remain. No calibration conversion is authorized.

### 25.43 Recovered the Astra/high output-limit failure

The tenth committed attempt in the second campaign reached the provider on
2026-09-08, received a hash-bound response, settled 29,850 micro-USD, and removed its
container. The receipt recorded 425 input tokens and exactly the configured 512
combined output tokens over 18,437 ms. Strict critique compilation failed, so the
attempt produced no success artifact. Exact use of the output ceiling strongly
supports truncation, consistent with OpenAI's definition of `max_output_tokens` as
including visible and reasoning generation, but retained evidence does not prove the
provider's exact terminal status or expose its raw body.

Brokered evaluation artifact schema 4 now preserves this distinct post-response
validation boundary. The repaired offline compiler bound sequence 10's independent
authorization, response-received audit, response hash, settled ledger entry, latency,
and cost into a non-scoreable `invalid_response` / `validation` artifact. The normal
live command now performs the same publication automatically with a structured
rejection event and exit code 2. It retains no raw response, prompt, provider request
ID, critique, or invented usage and fixes retry, automatic release, live-result
eligibility, and promotion to false. Recorded regression coverage exercises
incomplete output, automatic publication, offline recovery, reply-hash substitution,
and credential non-persistence.

Campaign v2 is halted and its unused eleventh and twelfth requests are not
authorized to run. The failed attempt breaks the Astra/high streak: although 15
authenticated successes remain historical evidence, current gate credit is 13 of
18. The four lower profiles remain complete, Astra/high requires three newly
precommitted consecutive successes, and Astra/max retains its first success. This
natural failure does not satisfy controlled boundary F4. A new public campaign and
budget disposition are required before any further provider request.

### 25.44 Sealed the replacement Astra campaign

A third private conformance manifest is sealed against the same blinded batch and
plan, the halted v2 manifest, and its terminal sequence-10 failure artifact. It
commits three fresh Astra/high attempts for a new consecutive streak followed by two
fresh Astra/max attempts for positions two and three. A deterministic lexical
selector excludes all six pre-v2 success IDs and all 12 v2 commitments, including
the failed request and unused sequences 11 and 12. The manifest commitment is
`df66aba92b145d243bf3cb5b378ec477ea81adafcf072286a250078b8f44b885`.

The sequence-10 boundary showed that 512 combined visible/reasoning output tokens
were insufficient. The replacement fixes each request at no more than 1,000 input,
2,048 combined output tokens, 60 seconds, and 112,400 micro-USD using the checked
Astra standard rates. Five per-request maxima total 562,000 micro-USD. A fresh
600,000 micro-USD ledger
`771cc6fcb438d44cbe2f51502bce2c9adc20bd26a89aa25fa17d57321c0ca9c6`
retains 38,000 micro-USD aggregate headroom and was empty and unblocked at sealing.

Sealing accessed no credential, reserved no spend, transferred no data, and sent no
provider request. It authorizes neither execution nor continuation of v2. Sequence 1
still requires fresh short-lived policies, independent authorization, operator
review, and explicit local consent. Any non-success stops v3. The current gate
remains 13 of 18, and successful completion of all five attempts would still leave
the five controlled failure boundaries and every downstream quality, calibration,
promotion, and activation gate outstanding.

### 25.45 Preserved the v3 pre-dispatch image failure

The first v3 sequence-1 invocation failed closed because its previously pinned
Docker image was absent locally. Policy and signature verification completed and the
API key entered ephemeral process memory, but the broker never recorded admission.
The audit remained `prepared`, the ledger remained `absent` with zero entries and
zero exposure, no container lifecycle existed, and no prompt or provider request
crossed the execution boundary. This is a local preparation failure, not a campaign
result, retry, controlled boundary, or change to the 13-of-18 gate.

The expired signed stub is preserved intact and cannot mint conformance evidence. A
locked rebuild produced no-volume image
`sha256:929977cba2903c990b567b1341f0d97b965ef31e670c73a4db30638204856dc7`,
which completed an offline, read-only, no-network smoke invocation and is now pinned
in the private v3 runner. A fresh authorization identity may be prepared against the
same committed sequence only after this public disposition. It still provides no
send authority without independent signing and new explicit operator consent; any
admitted non-success will halt v3.

### 25.46 Authenticated the first replacement Astra/high success

The first admitted v3 sequence completed against the corrected immutable container
boundary and was independently authenticated. It used 409 input and 438 combined
output tokens, including 203 reported reasoning tokens, over 13,730 ms. The shared
ledger settled 25,990 micro-USD against the 112,400 micro-USD request maximum and
retains 574,010 micro-USD with no unresolved or blocking state. Container cleanup
reached `removed` on its first attempt.

The completed artifact is
`2c94ce6d6126874368afa26fe0af9f30997615fc80670225d541120288590185`, the
observer-signed observation is
`fc821ec9ba65a54587c75f20ecae0b9b80e17ca36a278f681fdb407c3fea0b9d`, and fresh
authentication produced receipt
`07e85687a8093574301c37a1470edeef612606beb7dc9e8edd1b77c03cd604eb`.
All provider-authorship, billing, complete-batch, conversion, grading, scoring,
quality, promotion, and activation claims remain false.

This result begins a new Astra/high streak rather than joining successes across the
sequence-10 failure. Current qualifying progress is 14 of 18: four lower profiles
remain complete, Astra/high is 1 of 3, and Astra/max is 1 of 3. Sequence 2 requires
fresh no-send preparation, independent authorization, and explicit local consent.

### 25.47 Authenticated the second replacement Astra/high success

The second admitted v3 sequence completed through the same corrected immutable
container boundary and was independently authenticated. It used 373 input and 149
combined output tokens, including 124 reported reasoning tokens, over 8,701 ms. The
shared ledger settled 11,180 micro-USD against the 112,400 micro-USD request maximum
and now retains 562,830 micro-USD with no unresolved or blocking state. Container
cleanup reached `removed` on its first attempt.

The completed artifact is
`4c78321bfc90adb0fbb2149192af5d7522dcc07d6a85b357bbe852667f257b80`, the
observer-signed observation payload is
`450a050bae6f5eb3230be6e0ab0c05bf54c4b8b968e3f49ae5fa996ebc43f361`, and fresh
authentication produced receipt
`a637226ad6119f4b9878637613d8d4837ccdfc2d5e7675fd634dee42df971add`.
The distinct sample, request, authorization, audit, ledger-entry, response,
artifact, signature, and receipt identities prevent sequence-1 replay from
supplying this position. All provider-authorship, billing, complete-batch,
conversion, grading, scoring, quality, promotion, and activation claims remain
false.

This result is position two of the new Astra/high streak. Current qualifying
progress is 15 of 18: four lower profiles remain complete, Astra/high is 2 of 3,
and Astra/max is 1 of 3. Sequence 3 requires fresh no-send preparation, independent
authorization, and explicit local consent.

### 25.48 Completed the replacement Astra/high streak

The third admitted v3 sequence completed through the corrected immutable container
boundary and was independently authenticated. It used 392 input and 71 combined
output tokens, including 46 reported reasoning tokens, over 5,087 ms. The shared
ledger settled 7,470 micro-USD against the 112,400 micro-USD request maximum and now
retains 555,360 micro-USD with no unresolved or blocking state. Container cleanup
reached `removed` on its first attempt.

The completed artifact is
`7e5fa9b48e38ac21b69921a621e3af95235f00c3806a227f65a75898d30d86c8`, the
observer-signed observation payload is
`3301fb4d710c0108ade8ff1031c4c7af713e80ef19d36773796430b4f2610861`, and fresh
authentication produced receipt
`140022e6666d9d69a9e93d9afcf361ad856a7a58f2d307cd7226cdbb69c48101`.
All three replacement positions have distinct sample, request, authorization,
audit, ledger-entry, response, artifact, signature, and receipt identities. All
provider-authorship, billing, complete-batch, conversion, grading, scoring, quality,
promotion, and activation claims remain false.

This result completes the new Astra/high streak at 3 of 3. Current qualifying
progress is 16 of 18: five profiles are complete and Astra/max remains 1 of 3.
Sequence 4 begins the remaining Astra/max tranche and requires fresh no-send
preparation, independent authorization, and explicit local consent.

### 25.49 Authenticated the second Astra/max success

The fourth admitted v3 sequence completed through the corrected immutable container
boundary and was independently authenticated. It used 373 input and 206 combined
output tokens, including 181 reported reasoning tokens, over 6,411 ms. The shared
ledger settled 14,030 micro-USD against the 112,400 micro-USD request maximum and
now retains 541,330 micro-USD with no unresolved or blocking state. Container
cleanup reached `removed` on its first attempt.

The completed artifact is
`08490de0e3f399ff63813525103fd2e337b31d0c89e6b7809d78f00cf692f528`, the
observer-signed observation payload is
`01e47b33d54776f8991ab59777fdd3e784c68ff495e8df325e67257f118c5fa3`, and fresh
authentication produced receipt
`d27e63abf37d6d0e58999841ea7f8a3309e17ca8a29d950f1526351c953bb0da`.
Its sample, request, authorization, audit, ledger-entry, response, artifact,
signature, and receipt identities are distinct from the earlier Astra/max result.
All provider-authorship, billing, complete-batch, conversion, grading, scoring,
quality, promotion, and activation claims remain false.

This result is position two of the Astra/max profile. Current qualifying progress is
17 of 18: five profiles are complete and Astra/max is 2 of 3. Sequence 5 is the
remaining success assignment and requires fresh no-send preparation, independent
authorization, and explicit local consent. The success matrix alone will not satisfy
the gate because all five controlled failure boundaries remain outstanding.

### 25.50 Completed the OpenAI live success matrix

The fifth and final admitted v3 sequence completed through the corrected immutable
container boundary and was independently authenticated. It used 399 input and 349
combined output tokens, including 324 reported reasoning tokens, over 9,976 ms. The
shared ledger settled 21,440 micro-USD against the 112,400 micro-USD request maximum
and retains 519,890 micro-USD of unused campaign capacity with no unresolved or
blocking state. Container cleanup reached `removed` on its first attempt.

The completed artifact is
`937c80e6f0bb31da1114a1733f13379c275e2a4afe1888c78019cc2cc2ae3d55`, the
observer-signed observation payload is
`c7d8e67ce75dd4b80b4dfcf165b73daeee4f3dd230ac3de2563e98bd41604232`, and fresh
authentication produced receipt
`42f593529a9052da8d1d776b4955d7945b0e854f492ba012bdfe7cefa2b3c1fe`.
The three Astra/max positions have distinct sample, request, authorization, audit,
ledger-entry, response, artifact, signature, and receipt identities. All
provider-authorship, billing, complete-batch, conversion, grading, scoring, quality,
promotion, and activation claims remain false.

All six registered profiles now have three qualifying consecutive authenticated
successes, completing the 18-of-18 success matrix. Twenty successes remain in
historical evidence because the two pre-failure Astra/high results are retained but
do not count across the reset. The five-request v3 campaign is closed and its unused
ledger headroom authorizes no further send. The OpenAI live-conformance exit gate
remains incomplete until controlled boundaries F1 through F5 pass; only then may a
reviewed gate report consider calibration conversion.

### 25.51 Made F1 precredential rejection retainable

The real `openai-conformance` path can now write a canonical, content-addressed F1
receipt when an authentic signed authorization is expired or mismatched against the
current exact policy binding. The receipt binds the batch, sample, candidate,
request, spend policy, conformance policy, authority policy, signed authorization,
ledger, installed Mos Eisley version, and OpenAI SDK version. It records identical
before/after ledger snapshots and fixes credential access, audit creation, normal
output publication, container start, provider send, spend reservation, retry,
grading, scoring, promotion, and routing activation to false.

Receipt production is fail closed: malformed or invalidly signed authority cannot
mint one; an existing or overlapping receipt path is rejected; and any ledger entry,
ledger mutation, audit, assignment output, artifact, or lifecycle observation blocks
issuance. Tests exercise the actual CLI path while independently asserting that the
credential accessor and broker dispatcher are never called. This completes the F1
instrumentation, not F1 itself. The boundary still requires a reviewed run from an
installed wheel with retained operational evidence. F2 through F5 and all downstream
conversion, quality, promotion, and activation gates also remain outstanding.

### 25.52 Passed the installed-wheel F1 boundary

The first controlled failure boundary ran through a separately installed 0.1.0
wheel with SHA-256
`a7519afe7df26cc66ca94695e6e90be41723bb0b0e6b27c480af77f856702545`.
The operator independently signed authorization payload
`9d8fd80cfa82952f5581b8fe4acd188134936b45450a727321d5dd0227466cba`
against source conformance policy
`ae921f5eaf46c023b23b07b55e578c7532362b9fedefc7d8b63e1bbfaa2011f6`.
The installed command received target policy
`304ce847061259308de7e55ca6bccede82e1509dc1e9dbadf7e293836973834b`,
which differed only in the reviewed policy identity, and retained F1 receipt
`6a0d132074a27272851ddc0affe08ba3ce096a59e0f7ff68dc450489080941bf`.

Dedicated ledger
`5fa56e12fa183b0af7b18a4eb601560390e0b6b986e9c181272003ef5b9d95ad`
remained byte-for-byte unchanged with zero entries, zero charged, 10,000 micro-USD
available, no unresolved exposure, and no block. The exact ledger entry was absent
before and after. The receipt and independent filesystem check show no credential
access, audit, assignment output, conformance artifact, container lifecycle,
provider request, spend reservation, retry, grading, scoring, promotion, or routing
activation.

The first private verifier invocation completed and verified the one-use F1 command,
then failed while serializing only its final local summary because it passed a plain
dictionary to the contract serializer. The reporting wrapper was corrected and
resumed from the already-retained receipt; the controlled command was not rerun.
This post-boundary tooling defect does not alter the receipt or ledger evidence but
is retained in the disposition. F1 is complete; F2 through F5 and the reviewed gate
report remain outstanding.

### 25.53 Made F2 authentication rejection retainable

The real `openai-conformance` path can now retain a canonical status-`error` artifact
when an admitted request terminates specifically with `authentication_error` during
`token_count`. The artifact is compiled against the independently persisted
assignment authorization, terminal broker audit, and dedicated ledger. It requires
absent ledger state and null cost, while retry, automatic release, live-result,
grading, scoring, promotion, and routing authority remain false.

This path is intentionally narrower than generic provider-failure recovery. The
terminal audit classification and compiled artifact must agree on the exact F2
tuple. Partial audits and all other failure stages or categories
remain unable to publish an artifact; post-reservation ambiguity therefore retains
the existing conservative F3 behavior. Automated tests additionally prove the token
count is attempted once, generation is never attempted, no reservation or ledger
entry appears, and the full ledger snapshot is unchanged.

This completes F2 instrumentation, not F2 itself. A separately installed reviewed
wheel, disposable ledger, independently signed short-lived authorization, explicit
local consent, one deliberately invalid credentialed request, and retained
operational verification are still required. F3 through F5 and the aggregate gate
report also remain outstanding, and no provider request or downstream authority is
granted by this implementation.

### 25.54 Passed the installed-wheel F2 boundary

The second controlled failure boundary ran once through a separately installed
Mos Eisley 0.1.0 wheel with SHA-256
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`
and immutable image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`.
The operator independently signed authorization payload
`f19b0576522be558de6a85c3f1254e1cabab4d515486c6a7659778d03bee3e40`
and explicitly consented to one exact live token-count request using a deliberately
invalid disposable credential.

The request terminated after 1,498 ms with `authentication_error` at `token_count`.
Assignment authorization
`43c67406e1698bccbc401426278285c919906c6e81af777a2875e69a1754a8f2`
and terminal outcome
`c44cac0621f94234ee5029c3ccfc2dde9250924f1f2f7de0899fb3037d51cc14`
bind canonical failure artifact
`ee6cb8800a13985b38978d16b2d6cc54809fca23e6a1aa8930b0f466cb3bb3fa`.
It contains no response, provider request ID, usage, critique, or cost; generation was
never requested and retry, automatic release, live-result, promotion, and activation
authority remain false.

Dedicated ledger
`e00ec143a109677ce9e4be5cb7c0858e2e5099820b24e00843cd33b9ba0115a8`
remained unchanged at zero entries and zero charged with no unresolved or blocked
state. The exact prospective entry and both spend files are absent. Container cleanup
reached `removed` on its first attempt. This completes F2 but does not prove that
OpenAI inspected a particular request body or establish provider billing. The
18-of-18 success matrix plus F1 and F2 are complete; F3 through F5 and the reviewed
aggregate gate report remain outstanding.

### 25.55 Passed the installed-wheel F3 boundary

The third controlled failure boundary ran once through the separately installed
Mos Eisley 0.1.0 wheel with SHA-256
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`
and immutable image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`.
The operator independently signed exact authorization payload
`582c3e0f4455e11e65344c806b7527979d6b805b44178027483ca89150661dbd`.
The installed harness refused to run with an OpenAI credential available, used a
precommitted synthetic input count only to trigger normal spending admission, and
then injected one controlled `transport_error` at the `response` stage. No provider
request was sent.

Assignment authorization
`3ae79a0f3255f72943237a67213b15e029e82cd399312cc3c44afd0328907722`
and terminal outcome
`3e6b99a8e473ffecc28d940a3511f8f412d90a529f4790762dbc71534504b2ee`
bind reservation
`7aee410d8e0ff1118d0623f328c41377049792655d5e35d8f181b40c316c1914`
to uncertain spend receipt
`93d0aef34a888b5e08bc5bfa809db86f11a9107829a1e4cbf66ca101318e805f`.
The full 635-micro-USD reservation remains charged with null actual usage, and no
conformance artifact was published.

Dedicated disposable ledger
`70bae33b7b19656582d5f36c1bf669c2194d82e0adb83aa3e8b5e603e6296de7`
now contains exactly one unresolved `uncertain` entry, 635 micro-USD charged, and
9,365 micro-USD available. It will never be reset, released, or reused for a
successful probe. Retry and automatic release remain false; the container reached
`removed` on its first cleanup attempt. This completes controlled local boundary F3
but proves no OpenAI behavior, provider receipt, real token accounting, or billing.
The 18-of-18 success matrix plus F1 through F3 are complete; F4, F5, and the reviewed
aggregate gate report remain outstanding.

### 25.56 Passed the installed-wheel F4 boundary

The fourth controlled failure boundary ran through a separate installation of the
same Mos Eisley 0.1.0 wheel and immutable image used for F3. The operator
independently signed exact authorization payload
`20645429198674bf74229005fc78805f47aee358ba01fcca91c42af0c2a1b7b9`.
The installed harness refused to run with an OpenAI credential available and
returned one controlled Responses envelope with precommitted synthetic usage of 100
input and 20 output tokens but deliberately invalid `Critique` JSON. No provider
request was sent.

Assignment authorization
`d575a9b6cdc99fd78ba160878aa9255429239c8a3d1f9310c65a93c77b7db230`
and terminal response outcome
`0955e1b82225476fc75fb033d8f9e8fb72d2ff98daf1a15dac1780f1cfd56c8b`
bind response hash
`3a1034b648e1c6de05def3b031ccfd88accba49a0a248c1b852a1f2399d99c4f`.
The strict compiler rejected it and retained status-`error` artifact
`16304946b61a491af26010f35350c2b24d1ced3b08f3a54f04b64ba11363098d`
with `invalid_response` at `validation`. The artifact contains no provider request
ID, usage, critique, completed-result eligibility, retry, automatic-release, or
promotion authority.

Reservation
`67baaf6b9825d35837813a57957a5739eefd55d94688cc4c2c9faebb7029d7cc`
and settled receipt
`954bf0bad92ee966771d321b3b4cdeeaba2f7e2e0aa4ac6f8f2f1498ca78f2b0`
leave dedicated disposable ledger
`a89d76056904c1eb7702b52deea22c5706be1592e8b6d17279bb5ae2d7da4233`
with one settled entry, 44 micro-USD charged, 9,956 available, no unresolved
exposure, and no block. The ledger will not be reused for a successful probe, and
the container reached `removed` on its first cleanup attempt. This completes F4 but
proves no OpenAI behavior, provider authorship, real token accounting, or billing.
The 18-of-18 success matrix plus F1 through F4 are complete; only F5 and the reviewed
aggregate gate report remain outstanding.

### 25.57 Passed the installed-wheel F5 boundary

The fifth controlled failure boundary ran through another separate installation of
the reviewed Mos Eisley 0.1.0 wheel and the immutable image used for F3 and F4. The
operator independently signed exact authorization payload
`fcb4077d726d4c924b49d28c3121066c9efa53511814573fb869393db5647f25`.
The installed harness refused to run with an OpenAI credential available and used a
no-network transport that blocked only after normal broker admission and spending
reservation. No provider request was sent.

Assignment authorization
`a1da497479fa4ceb729c5c7c2f22233d0aa97100fa0b324826722d36fbaaebf3`
and admission
`414adef78d436f07fa4a78cb51d20cf6687cc2866b3db57b8daf6ee7d809f5d3`
preceded held reservation
`d61a95be7e621a2ebb49cc55c30aaeee37e094ca2769cc8a77c10c0e7c8dbf1c`.
After independently observing the held entry and armed watchdog, the harness killed
its own launcher with SIGKILL. The launcher could not execute normal cleanup.
Independent watchdog result
`5166fca1bd66c9755ae6c82a6eb761830f2b0ca3f87077b930f6c73f5580a1a2`
removed exact container
`890bb4c6c1190c86c590d8910bcdc34cf6d85fedd9c9c0b1650c76278a480e30`
on its first attempt, and a separate Docker query confirmed that it is absent.

Dedicated disposable ledger
`156724341d384d8746e90b240875633178d7fd0945f6a0d40562ef8be38e3635`
now contains exactly one unresolved `held` entry, 635 micro-USD charged, and 9,365
available. It will never be reset, released, retried, or reused. Read-only recovery
reports phase `admitted`, with no terminal outcome, spend receipt, conformance
artifact, success, or failure claim. Retry, automatic release, and promotion remain
false. This completes F5 but proves no OpenAI behavior, provider receipt, or billing.

All 18 success positions and F1 through F5 now exist, completing the 23 required
execution positions. The overall gate remains open until a reviewed aggregate report
reverifies the complete lineage and fixes every unsupported downstream claim to
false. No calibration conversion or provider request is authorized by this result.

### 25.58 Passed the aggregate OpenAI live-conformance gate

An offline, credential-refusing compiler reauthenticated all 20 retained successful
exchanges at their original authentication timestamps against the exact frozen batch,
policy, observer signature, assignment, artifact, broker audit, and ledger source.
It counted 18 qualifying positions across the six required profiles and separately
retained the two earlier Astra/high successes invalidated by the sequence-10 break.
Every sample, receipt, signature, artifact, authorization, outcome, provider request,
provider response, and ledger-entry identity is distinct.

The aggregate also reverified the v2 terminal validation failure, the v3 pre-dispatch
no-send event, both expired unsigned preparations, both forbidden v2 continuations,
all three campaign manifests, every success-ledger entry, and F1 through F5 from
their authoritative sources. The private 32,624-byte sorted compact report hashes to
`e58dc274b5087271fe1f241724fdd1f319956b4fffba8bf1e83e086db26ea72a`
and records 23 of 23 required execution positions with `outcome=pass`.

The compiler accessed no credential and sent no request. Provider authorship,
billing reconciliation, quality, complete-batch conformance, calibration conversion,
grading, scoring, promotion, routing activation, and additional-request authority
remain literal false. Passing this gate permits only the design of a separate,
reviewed offline converter for the 18 qualifying records. No conversion or empirical
routing claim exists yet.

### 25.59 Implemented partial OpenAI conformance calibration conversion

A committed conversion policy now pins the exact passed aggregate-report digest,
frozen plan and 360-assignment batch, six profiles, and 18 qualifying position names.
The offline converter requires exactly those 18 authenticated receipts and their
matching brokered artifacts. It rechecks canonical receipt/artifact hashes and every
sample, route, request, authorization, outcome, response, ledger, latency, cost,
usage, and critique binding against the aggregate before restoring frozen batch
order. Invalidated historical successes, omissions, additions, substitutions,
noncanonical reports, changed pass claims, and any newly granted authority fail
closed.

The command requires explicit offline consent and refuses to run while either
supported OpenAI key variable is present. Its first real conversion accessed no
credential, sent no request, and produced a private 30,592-byte seed with SHA-256
`c67dfcfac073ba4946afd59b2f2960fb9de10740654cdaf8ad1183f91e8cf570`.
The seed contains 18 of 360 assignments and the same 135,812 micro-USD local cost
total as its sources. It is deliberately incompatible with `RawResultSet`, exposes
route identity, and fixes complete-batch coverage, provider authorship, billing,
quality, grading, scoring, promotion, activation, and further request authority to
false. A complete-batch brokered calibration and separately reviewed gradeable
issuance boundary remain required.

---

