# Changelog

Notable changes are recorded here using semantic versioning.

## Unreleased

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
