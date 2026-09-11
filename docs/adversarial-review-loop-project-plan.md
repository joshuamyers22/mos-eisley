# Adversarial review loop — revised Mos Eisley project plan

Reviewed 2026-09-08. Status: planned integration over the existing recorded core.
Revises `/Users/josh/Downloads/adversarial-review-loop-project-plan.md`;
the original remains an input reference. Its referenced *Design Plan* was not
present among the supplied local documents. Definitions below are explicit Mos
decisions, not reconstructed claims from that missing document.
See [project review](PROJECT_REVIEW_2026-09-08.md),
[adaptive routing](adaptive-reasoning-routing.md), and
[main plan §26](mos-eisley-plan.md#26-integrated-project-review-and-delivery-contract).

## Product and sequencing decisions

Reuse Mos's controller, review contracts, private artifacts, evaluation lineage,
spending admission and containment gates. Keep local files/SQLite as the default;
remote storage remains a user choice subject to owner isolation. No mandatory
Postgres, research-site GUI, email notification or second orchestration framework.
Deliver initial contracts and demonstrations with recorded providers alongside
the conversational controller. Live reads require provider gates; tests and writes
require isolated execution; delegated coding also requires E2.

Deterministic tools decide mechanical checks they can substantiate. Linguistic
lint such as pronoun or modifier warnings is advisory: it cannot prove a plan is
unambiguous or invalidate a requirement merely because it uses "may". Version the
project rubric and explicit blocking rules. Architecture/security objections that
need judgment remain reviewable when tied to a requirement, threat or impact;
inability to encode a linter does not make them irrelevant preferences.

Stage 0 is an experiment in earlier defect prevention. High overlap with later
findings does not prove the later reviewer is unnecessary: both stages can detect
the same requirement and still miss different implementation defects. Retain final
implementation review until a paired ablation demonstrates safe reduced coverage.

## Definitions and immutable identities

Use separate fields for failure cause, plan-reading divergence and adjudication:

| Dimension | Values and meaning |
|---|---|
| Defect class | A: ambiguous, absent or contradictory requirement; B: implementation violates a specified requirement; C: independent security, robustness or operational defect supported by a trusted invariant or impact argument |
| Reading divergence | Ambiguity: multiple conflicting permitted readings; gap: required behavior unspecified; benign: different wording/implementation with equivalent observable obligations |
| Objection disposition | Upheld, dismissed, or unresolved; retain category, impact, evidence and rationale separately |
| Execution status | Passed, assertion failed, build/binding failed, unavailable, timeout, cancelled, or not run |

These are proposed labels for future versioned schemas; current `Finding` and
`Verdict` are not silently reinterpreted. Mixed defects can link more than one
class. Class C does not authorize invented requirements: when evidence is
insufficient, create a requirement-gap issue and resolve intent before demanding
code changes. Neither a test failure nor two unsuccessful fix cycles proves A.

Give clauses stable IDs scoped by plan ID and immutable revision digest. Each
clause records normative text, source/authority, interfaces, units and failure
behavior where applicable, and acceptance obligations. Cite `(plan digest,
clause ID, clause text digest)`; edit text by creating a revision, and tombstone
removed IDs rather than reusing them. Persist requirement-to-test-to-finding links.
All evidence also pins the code tree, test package, binding, execution environment
and run. A digest authenticates identity, not clause meaning or test correctness.

## Phase L0 — contracts and bounded instrumentation

Build the clause template/linter, typed stage/outcome records, requirement coverage
map and explicit state machine over the existing canonical protocol. Map records
through §17.5; retain content in private evidence, not ordinary telemetry. Add the
decision-time routing fields in the routing design even while choices are fixed.
Use brief, request, artifact and policy digests for replay; require schema migrations
to preserve old replay semantics or reject old versions clearly.

Exit: a recorded task produces linked plan/test/finding records without invented
values; duplicate/stale clauses, unavailable checks, storage failure and incomplete
stages remain distinguishable. Existing cassette replay remains deterministic.
Missing or invalid required evidence cannot produce acceptance.

The proposed persisted workflow uses these transitions; evidence status and code
verdict are separate fields. Each transition records the task revision, guard
evidence and remaining budget atomically before releasing dependent work.

| State | Allowed next state and guard |
|---|---|
| Draft | Readings sealed in the Stage-0 profile, otherwise plan review; frozen plan/tests exist |
| Readings sealed | Plan review after both valid commitments and disclosure; incomplete on a missing reader |
| Plan review | Approved after judge acceptance and creator approval of exact revisions; otherwise revised draft or unresolved |
| Approved | Implementing after matching child grant and execution/E2 gates |
| Implementing | Verifying after integration and locked reviewer test/binding packages |
| Verifying | Final review after all required checks pass; evidence triage for a failed or disputed check |
| Evidence triage | Correcting for an adjudicated implementation defect with remaining budget; revised draft for a plan/test defect; infrastructure error or unresolved when correctness cannot be established |
| Final review | Accepted after final independent verdict; correcting only with an upheld finding and remaining cycle budget |
| Correcting | Revised draft for plan/test changes, otherwise implementing; invalidate affected receipts and consume the task cycle |
| Any active state | Cancelled, infrastructure error, or unresolved on its corresponding failure; never accepted by default |

Terminal tasks remain inspectable. Resume validates committed state and input
digests, accounts for uncertain in-flight work, and preserves consumed budget;
it does not replay effects just because a completion record is missing.

## Phase L1 — independent plan readings and creator approval

The creator first drafts the plan and its executable acceptance tests, preserving
§15.7. Two fresh readers receive the same frozen plan, rubric and declared interface
context, without creator reasoning, creator tests or the other reading. Treat a
creator-context reading as an author statement, not independent evidence.

Each reader seals worked examples, interface/error signatures and acceptance
obligations with specified/inferred/not-addressed tags. The trusted controller
records exact input identity and commitments before revealing either output. A
timeout or crash before both commitments means incomplete comparison, not agreement.
Commitments use controller-authored manifests and separate access scopes; merely
asking models to keep a secret is insufficient. Compare semantics with evidence,
not string inequality; retain originals.

Resolve observable contract conflicts before implementation. Then a critic reviews
the exact creator plan/tests plus the reading findings; the judge adjudicates and
the creator approves those exact revisions. Unsettled product intent returns to
the user when necessary; internal implementation choices can be resolved by the
creator within the authorized requirements. An agent's approval grants no new
machine or provider permission.

Exit: leak probes confirm readers cannot see tests/other commitments; revisions
invalidate dependent approvals; ambiguity, gap, benign and unresolved rates have
declared denominators. Template edits follow actual recurring defects. Gate A
compares deterministic-only versus added readings on matched tasks, counting
review cost, needless plan changes and downstream defects. Inconclusive results
keep Stage 0 experimental and retain existing review coverage.

## Phase L2 — derivation, binding, and isolated execution

After approval, delegate coding under §14.2.1; creator-owned tests remain mandatory.
Separately derive reviewer tests from the approved plan/interfaces in a fresh
context before revealing implementation or author telemetry. Reviewer tests
supplement the creator suite. Uncitable objections are retained as possible
requirement gaps or trusted-invariant concerns, not silently deleted from evidence
or transformed into automatic code-change demands.

Freeze a test package including assertions, inputs, fixtures, expected values,
parameters, oracles, skip/xfail markers and collection configuration. Bind it to the
implementation through a separate allowlisted adapter. Hash the frozen package
before and after; inspect all binding/dependency changes, not only `assert` ASTs.
An adapter can fake results, monkeypatch behavior, swallow errors or collect zero
tests without editing an assertion. Require collected/executed/skipped counts,
an audited adapter surface, and known-good/known-bad controls that exercise the
actual implementation. Reject empty collection and unapproved skips. Semantic
equivalence of arbitrary executable test code is not presumed provable by a diff.

Binding incompatibility or excessive cost produces a binding/plan finding and a
new reviewed revision; it does not justify loosening the oracle. Pin dependencies,
environment/image, randomness and time inputs. Run in the isolated test broker with
no credentials, raw network, sibling artifacts or host writes. Apply CPU, memory,
PID, output, disk and wall-clock limits and descendant cleanup. Tests are hostile
code even when generated by a reviewer.

Retain execution receipts and all results. Reveal author telemetry to the reviewer
only after the package is locked and execution evidence exists; blind derivation
ends at that boundary. Any subsequent derived test starts a new versioned pass.
Flaky results, import errors, timeouts and unavailable checks remain distinct from
reproduced requirement violations. Reruns need a bounded declared policy.

Exit: negative fixtures catch assertion-preserving oracle changes, fixture/input
changes, fake bindings, skip/xfail, zero-test runs, stale trees, nondeterminism and
resource escape. A current final verification run covers both creator and reviewer
suites; dropping an optional reflection pass never drops required verification.

## Phase L3 — evidence triage, correction, and final review

Initially every proposed blocking correction goes through the existing full judge
path. Require a current artifact, reproduced failure, applicable clause/invariant
and evidence of an implementation violation. A citation's existence proves neither
aptness nor that the test oracle is right. Invalid tests, infrastructure failures,
plan gaps and implementation defects take different paths.

Give the creator bounded per-finding notes and relevant failing evidence for repair.
Keep passing/unrun reviewer details out of that initial correction packet if the
registered blindness protocol requires it; retain them for the controller, judge,
owner inspection and final whole-suite verification. Limited disclosure cannot
hide incomplete coverage or unresolved evidence in the final result.

Author rejection forces adjudication; it is not itself ground truth. The judge
receives identity-stripped structured evidence and can uphold, dismiss or mark
unresolved per objection. Require the configured critic/provider quorum, freeze the
roster per review, and fail visibly when diversity is unavailable. Distinct provider
roles reduce direct self-review but do not establish statistical independence.
Judge order permutations are logged for replay and consistency measurement.

Default bounds: at most two critique/rebuttal rounds per artifact and two correction
cycles per task, further restricted by the predeclared task time/cost budget.
Artifact revisions consume that same task budget and cycle count. Counters persist
across restart; cancellation and exhaustion stop descendants and retain unresolved
findings. Repetition does not automatically relabel a defect as plan ambiguity.
Keep `infrastructure_error` separate from code dispositions; a proposed richer
workflow status must map to existing CLI codes until a versioned change ships.

After integration, freeze the final tree, run required checks, and obtain independent
critic/judge review of implementation and evidence. Acceptance applies only to those
digests with all required obligations satisfied. Any later edit invalidates the
affected verification and acceptance. User steering that changes scope creates a
new plan revision and invalidates dependent work without resetting spent budget.

Exit: deterministic transition tests cover stale approval, invalid evidence,
partial quorum, conflicting tests, renewed revisions, restart/cancellation and
budget exhaustion. No sampled or automatic bypass ships in L3.

## Phase L4 — useful measurements and independent labels

Monitor self-consistency, author rejection, citation aptness, binding cost, coverage,
stage overlap and latency as diagnostics. Track escaped defects both dismissed
by the judge and never raised by a reviewer, using an explicit follow-up window;
missing follow-up stays unknown. Low rejection can mean author acquiescence, and
consistent judges can be consistently wrong. Neither is an accuracy estimate.

Start a small independently graded calibration/holdout set before any automatic
correction bypass, review removal, route downgrade or quality claim. Reuse Mos's
dual authenticated grading and disjoint resolver. A GUI is optional; a private
CLI/file labeling queue is sufficient. Judge predictions remain hidden until
labels are sealed. Labeler repeat agreement is diagnostic, not a proven ceiling
on accuracy. Fix weak rubrics/disagreements rather than declaring one signer an oracle.

Sample ordinary accepted, rejected, clean and defective tasks as well as escaped
defects, disputed cases and cross-family disagreements. Preserve each inclusion
probability, overlapping sampling channels, nonresponse/age-out reason, and group
identity. Do not infer population rates from only difficult harvested cases.
Unknown sampling probability means descriptive-only evidence. Queue caps may defer
work but cannot silently delete hard cases from accuracy denominators.

Keep development regression fixtures separate from promotion holdout. A case exposed
to coding, prompt tuning, templates, retrieval or routine regression becomes
development data; it cannot later be fresh holdout. Enforce access before packet
construction, including caches, notes and attachments, rather than only in SQL.
Related tasks and revisions stay in one split. Holdout reuse is not justified by a
new filename or policy digest; adaptive reuse can overfit the evaluation itself.
See [Dwork et al.](https://arxiv.org/abs/1506.02629). Mos retains independent custody
and a once-used holdout instead of claiming a reusable-holdout algorithm.

## Phase L5 — controlled simplification and routing

Gate B asks whether sufficient independent evidence supports the proposed decision,
not whether overlap or self-consistency looks stable. Defer a labeling GUI or large
dataset until useful, but never waive required independent evidence. Preserve
full review/fixed routes when the data is insufficient.

Preregister paired whole-task comparisons: deterministic checks only versus added
Stage 0; one critic versus N critics versus N plus judge; full judge coverage versus
a proposed sampled path; and fixed versus cheaper reviewer/routing policies.
Respect the same authority limits in every arm. Evaluate both clean and defective
tasks, grouping related trajectories and including all rework and abandoned-task
cost. Review-stage overlap is descriptive; marginal caught/escaped defects and
correct-work damage decide whether reduced coverage passes.

Define correct-work damage as an independently adjudicated unnecessary requested
change or regression introduced by the loop on an initially acceptable task;
report these separately and as a combined any-damage rate. Denominator: all
independently established initially acceptable tasks, not only author rejections.
Set the absolute damage ceiling, non-inferiority margin, detection/completion
floors, minimum worthwhile whole-task savings, p95 latency ceiling, family correction
and required sample size before results. Missing follow-up, weak power or zero
verified successes cannot qualify a cheaper policy. No universal "50–100 per
bucket" or bootstrapped zero-error interval establishes a rare-damage bound.

Only after this gate may a versioned policy propose sampled judging, with forced
adjudication for rejections, unverified citation aptness, high-impact defects,
binding churn, disagreements, unknown outcomes and control violations. Retain a
random audit of the ordinary path with known inclusion probability. Drift or failed
audits restore the qualified full-review path or stop. Sampling cannot remove
final required checks or turn unchecked findings into automatic acceptance.

Adaptive reasoning follows [R0–R4](adaptive-reasoning-routing.md#delivery-gates).
Whole-loop causal effects, output-budget routing and cross-family transfer need
their own evidence; the Phase L4 proxy stream does not automatically train or
activate a safe router.
