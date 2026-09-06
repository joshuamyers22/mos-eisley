# Changelog

Notable changes are recorded here using semantic versioning.

## Unreleased

- Add an independent maximum-60-second Ed25519 authority that binds one exact
  admitted skill-runtime request, route, controls, default, and held spend entry.
- Add durable at-most-once consumption under fresh local guards while deliberately
  issuing no bearer grant, authorizing no direct provider dispatch, and sending no
  request.

- Add independent Ed25519 authorization for one exact state-bound skill default
  transition, including installed provenance, latest release control, sequence, and
  expected prior pointer.
- Add a private SQLite default store that atomically consumes the decision and updates
  an immutable revision chain plus current pointer while continuing to deny runtime
  lookup, activation, and all other configuration mutation.

- Add a private content-addressed installed-skill store that consumes exact one-use
  authority, serializes cross-process commits, reconstructs every written byte, and
  durably publishes only completion-marker-last atomic transactions.
- Add read-only install recovery correlation for completed, incomplete, claim-only,
  and unbound states while continuing to deny default changes, runtime lookup,
  automatic recovery, and cleanup.

- Add independent Ed25519 installation authority for exact quarantined persona
  packages, binding the latest release-control anchor, staging manifest, one-use
  claim-store identity, installation target, action, and bounded validity window.
- Add a private durable at-most-once claim ledger and guarded consumption primitive
  that burns authority before side effects and holds release control through the
  caller's commit, while granting no activation or configuration mutation.

- Add a private content-addressed skill quarantine store with exact post-write archive
  reconstruction, semantic verification, completion-marker-last transactions,
  durable atomic rename, idempotent verified reuse, and bounded crash inventory.
- Reauthenticate the complete skill-release lineage and hold a latest-control SQLite
  read guard across staging commit, closing the local check-to-revocation race while
  preserving literal installation, activation, and configuration denial.

- Add independent, expiring Ed25519 skill-release allow/revoke decisions that
  reverify complete release provenance, enforce separation from promotion and
  evaluation authorities, and optionally bind exact retained rollback bytes.
- Add a release-scoped private append-only anchor with a pinned bootstrap floor,
  increasing sequence/time, irreversible revocation, exact latest-state checks, and
  literal denial of installation, activation, and configuration mutation.
- Harden semantic archive verification so in-process objects with copied deployment
  authority fail closed as JSON-loaded archives already did.

- Add current skill-release evidence that semantically reverifies a retained package,
  recomputes both authenticated evaluation lineages, and binds the exact archive to
  its signed promotion receipt while literally denying installation, activation,
  and configuration mutation.
- Add a host-clock CLI gate and adversarial tests for package substitution, receipt
  expiry, evidence tampering, full-lineage verification, and private output.

- Add deterministic retained skill-package archives containing every immutable
  validated byte, per-file and whole-package commitments, semantic descriptor and
  instruction revalidation, explicit project opt-in, and literal denial of
  extraction-adjacent installation, activation, and configuration authority.
- Add private archive and non-extracting verification CLI commands plus adversarial
  coverage for byte tampering, reordering, reserved script paths, forged semantics,
  and authority escalation.

- Add independent Ed25519 persona-skill promotion requiring both fully reverified
  split reports, authority separation from graders/resolvers, policy-bounded expiry,
  deterministic decision recomputation, and literal runtime/configuration denial.
- Add derive/authenticate CLI commands that never accept promotion private keys,
  plus adversarial tests for failed gates, stale decisions, key overlap, and tampering.

- Bind exact inline or persona-skill instructions into evaluation route/request
  identity, including a validated skill-body digest; version skill, candidate/grid,
  plan, and execution contracts accordingly.
- Add sealed paired persona-skill comparisons with prompt-only experimental control,
  fixed independent-group Hoeffding/Bonferroni inference, full dual-grade lineage,
  resource deltas, and literal promotion/activation denial.
- Add an atomic private one-use holdout claim plus seal/score CLI commands and
  adversarial tests for route confounding, underpowered groups, replay, and tampering.

- Add a narrow prompt-only skills foundation with standards-compatible `SKILL.md`,
  an optional validated `mos.yaml`, source-qualified whole-package digests,
  immutable bounded snapshots, explicit project activation, and schema-2 recorded
  run provenance. Executable, credential, and authority-bearing extensions remain
  rejected or deferred.

- Add a pinned append-only routing-control anchor and read-only runtime preflight
  that reject older-message replay, preserve revocations monotonically, reverify the
  complete evidence chain, expire within a signed short window, and grant no dispatch
  or configuration authority.

- Add short-lived routing activation eligibility that fully reverifies authenticated
  promotion and requires three distinct, evaluation-independent Ed25519 signatures
  over exact route/cost/freshness policy, operational attestations, and revocation
  control while denying substitutions, runtime activation, and configuration writes.

- Add independently authenticated routing promotion with policy-level thresholds
  pinned before holdout, deterministic denial on missing or failed evidence, full
  lineage recomputation, Ed25519 authority separation from graders/resolvers, and
  literal runtime-activation denial.

- Add one-attempt frozen-policy holdout evaluation with a private exclusive local
  claim, full calibration/holdout lineage recomputation, profile-level adequacy,
  under-routing, fallback coverage, conservative cost/latency regret, and literal
  promotion/activation denial.

- Add deterministic calibration-only candidate-policy freezing with sealed role
  floors, complete-cost requirements, explicit fallback/fail-closed decisions,
  full lineage recomputation, and literal holdout/promotion/activation denial.

- Add calibration-only scoring for sealed prompt profiles from fully reverified
  dual-grade lineage, with simultaneous confidence correction across every profile,
  route, metric, and both splits and literal promotion/activation denial.

- Add a non-activating, content-addressed routing-study protocol that binds exact
  label-free prompt features, pre-registered numeric partitions, role candidate
  floors and fallbacks, a cost-first objective, and freeze-before-holdout rules.

- Add a dual-lineage scorer that reverifies every private source and authenticated
  grading artifact, uses the existing fixed-matrix statistical engine, retains all
  provenance digests, and emits only literal non-promotable reports.

- Add an offline dual-lineage observation compiler that reconstructs the private
  execution/grading chain, reverifies the complete authenticated resolution, and
  emits a distinct legacy-incompatible contract linked to every source policy and
  digest.

- Add an offline dual-authenticated grading gate that reverifies two distinct
  Ed25519 graders, preserves both signed originals, and requires a policy-disjoint
  signed resolver to cover every conflict exactly. The resulting lineage remains
  explicitly non-promotable and disconnected from compilation and scoring.

- Add Ed25519 authentication for exact route-blind human adjudications, with unique
  public-key trust policies, domain-separated signatures, reverifiable receipts,
  and a verification-only CLI that never accepts grader private keys.

- Add an explicitly acknowledged, one-assignment `openai-conformance` command with
  loop-local SDK clients, immutable offline worker isolation, independent trusted
  authorization, crash-conservative audit/spend records, and non-scoreable output.

- Add a deterministic blinded OpenAI conformance request with strict structured
  `Critique` output, verified through the installed SDK using synthetic transport.

- Compile fully validated broker responses into assignment/audit/spend-bound
  conformance artifacts with usage and hash-linked latency; keep them non-scoreable.

- Bound decoded non-streaming OpenAI HTTP response bodies before SDK model parsing;
  reject compressed/chunked oversize bodies and streaming operations.

- Add `broker-audit-status` for explicit, independently anchored, read-only crash
  inventory; reject self-attestation and never retry or release spend.

- Add crash-conservative broker recovery inventory that cross-checks assignment
  audit phases with exact shared-ledger entry state and never authorizes retry.

- Connect request-bound grants to offline containers through bounded private pipes;
  test tampering, replay, framing, disconnect cancellation and exact cleanup.

- Add host-owned, exact-request single-use provider grants with mandatory shared
  spending admission and adversarial fixture tests; live evaluation remains gated.

- Replace aggregate adjudication with schema-2 per-finding decisions; derive
  detections and false positives and reject unresolved or incomplete grades.
- Add `eval-agreement` for source-bound, descriptive two-grader conflict reports.

- Gate offline route scores on independent group means with fixed-design
  Hoeffding/Bonferroni bounds; preserve pooled Wilson metrics as diagnostics.
- Reject cross-split groups and duplicate briefs; mark missing grouping ineligible.
- Version dataset/gate/plan/report schemas to 2 and report promotion readiness false.

- Generate the production Python CLI baseline from template commit 3d467040.
- Add recorded blind review, quorum, citation validation and policy verdicts.
- Add private artifacts, request-bound cassettes, SQLite metadata and verified replay.
- Add negative tests, strict typing, coverage and package/container checks.
- Add a provider-neutral multi-turn agent protocol and deterministic model registry.
- Add bounded iterations, tool counts, byte budgets, effort fallback and deadlines.
- Add an inert fixture dispatcher, crash-boundary journal and verified agent replay.
- Add the official OpenAI Python SDK and a Responses API canonical adapter.
- Add an explicitly acknowledged, no-tools OpenAI prompt command and live artifacts.
- Track provider tokens separately from local canonical byte safety limits.
- Specify evaluation-gated prompt-difficulty routing across backend, model and effort.
- Add content-addressed offline sweep planning and exact-coverage split scoring.
- Add blinded recorded evaluation execution and provenance-bound adjudication.
- Reject incomplete grading matrices and judgments inconsistent with empty outputs.
- Incorporate the Codex-parity adversarial review and gated extension delivery plan.
