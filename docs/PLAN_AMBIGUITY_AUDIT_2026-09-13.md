# Plan ambiguity audit — 2026-09-13

Status: findings and proposed resolutions for owner review. This report changes
neither the product requirements nor runtime policy. Implementation and further
plan amendments are paused pending this review.

Baseline: `ce538762b3be4c33c3c67a4feee705c0d485584c` (main before PR #221).
PR #221 was withdrawn without merging, and its two running CI workflows were
cancelled. Its new §7.7.1 is excluded from this audit's evidence. Josh's clarification
that author, critic and judge are model roles remains the governing user instruction.

## Scope and method

Compared the main plan's normative product, role, review, permission, storage and
release sections with the roadmap, revised review-loop and routing designs, and
the relevant approval/conformance documentation. Checked the earlier integrated
project review to avoid presenting its resolved findings as new discoveries.
Historical implementation receipts were treated as evidence of particular features,
not as new universal product requirements. Selected code contracts corroborate the
current roster and approval behavior; this is not a complete code/security audit.
Current vendor model availability, prices and API specifications were not reverified.

The model-role design already exists in §7.7 and the complete authoring sequence
already exists in §15.7. Neither needs to be invented again. The previously discussed
human-signing detour is known context, not counted as another new finding below.

## Findings

| ID | Ambiguity or specification gap | Resolve before |
|---|---|---|
| A01 | Default critic count and the scope of diversity/quorum | Normal G2 roster selection |
| A02 | Scope and lifetime of operator approval | Normal G2 dispatch |
| A03 | Component conformance versus completion of G2 | Selecting the next live test or claiming G2 complete |
| A04 | Exact meaning of review rounds, corrections and repair allowances | Multi-round implementation |
| A05 | New instructions versus replacement of the active objective | Author compaction |
| A06 | Which quality-study prerequisites apply to ordinary correction | G4 production activation |
| A07 | Meaning of encryption at rest for local and remote storage | Storage qualification |
| A08 | Feature scope of version 0.1.0 versus the finished product | Release commitment |
| A09 | A single authoritative current work item | Resuming implementation |

### A01 — Default critic count and diversity/quorum

**Decision, 2026-09-13:** resolved by Josh. The standard workflow assigns one
distinct model family to each top-level role: author, critic and judge. Every
top-level role may delegate work to subagents. Subagent routes may cross model
families and are selected under the existing task-difficulty, capability, quality,
cost and aggregate-budget policy. A subagent remains subordinate to the role that
created it and does not become a fourth top-level review role. Each subagent instance
and its private context remain isolated to its owning role. Output crosses into
another role only through an explicit controller-defined, frozen artifact handoff;
private reasoning, transcripts, sibling outputs and ambient context never cross.

**Evidence:** [§7.7](mos-eisley-plan.md#77-interchangeable-creator-critic-and-judge-roles)
defines a three-provider creator/critic/judge profile and six role permutations.
The `[roster.default]` example in
[§16.3](mos-eisley-plan.md#163-config-layering) instead supplies three critics,
including models also assigned as author and judge. The existing
`ReviewPolicy` defaults require two critics from two providers, and
`review.pipeline.validate_roster` counts provider diversity among critics only.
[Review acceptance](REVIEW_CONFORMANCE_ACCEPTANCE.md)
also explicitly distinguishes one-provider experiments from that default policy.

**Impact:** a normal author + one critic + judge selection can fail quorum even
when its three roles use different providers. Reusing the sample can instead
produce a larger panel and direct model self-review. Distinct model assignments,
distinct providers across roles, and critic quorum are different checks.

**Required plan correction:** make that decided three-family workflow the normal
profile, with one required critic. Define cross-role family separation separately
from critic-response quorum. Keep larger critic panels as explicitly named profiles
with their own quorum and cost. Update the existing example and extend existing
contracts where necessary; do not create a competing role system. Reference §7.3's
difficulty routing and extend §14.2's general subagent rules to all three top-level
roles; retain §14.2.1's author-owned implementation duties. Explicitly distinguish
top-level family separation from cross-family subagent routing. Preserve context
separation, frozen handoffs, least privilege and aggregate task limits. No further
product choice remains for this finding.

### A02 — Scope and lifetime of operator approval

**Decision, 2026-09-13:** resolved by Josh. The standard is one explicit bounded
task approval covering the author, its permitted implementation subagents, critic,
judge and bounded correction cycles. It remains valid only within the approved
providers/data scope, machine capabilities, aggregate spending ceiling and lifetime.
Trusted user configuration may narrow that default by requiring approval at finer
boundaries, such as each review phase or subagent. Project content and model output
cannot broaden, renew or bypass approval. Any increase in scope, authority, spend or
time requires a new user approval; revocation stops later dispatches while preserving
completed and uncertain effects.

**Evidence:** [§16.0](mos-eisley-plan.md#160-conversational-product-contract)
says a fix/build request authorizes relevant work within policy and approvals occur
at real policy boundaries. [§15.7](mos-eisley-plan.md#157-plan-review-creator-approval-and-delegated-implementation)
separates creator-model acceptance from user permission. The current
[terminal approval flow](REVIEW_APPROVAL_FLOW.md) demands one exact hash approval
for critics and another for the evidence-derived judge request; ordinary `yes`
declines. The signed-probe documents describe still another authorization layer.

**Impact:** the product contract does not say whether a user's bounded task approval
covers the later judge request and ordinary correction attempts, or whether every
phase must stop for another user interaction. Removing human signer requirements
alone does not settle that question. It also leaves the relationship between a
session allowance, a task allowance and phase approvals unclear at the UI boundary.

**Required plan correction:** define the decided operator grant and configurable
narrower approval modes. Let the controller derive exact phase requests only inside
the grant and retain their identities. Keep creator-model plan acceptance as a
separate internal workflow record. Document revocation, resume and changed-artifact
behavior explicitly. This decision defines the replacement product path; it is not
permission to skip checks in the existing signed APIs.

### A03 — What evidence closes G2?

**Decision, 2026-09-13:** resolved by Josh. G2 requires recorded tests covering
all six assignments of Claude, GPT and Gemini to author, critic and judge, plus one
budgeted live end-to-end run with a distinct model family in each role. An OpenAI-only
or single-model campaign is intermediate component evidence and cannot close G2.

**Evidence:** roadmap [item 3](ROADMAP.md) sequences OpenAI critic/judge integration
before other providers. [G2 in §26.4](mos-eisley-plan.md#264-delivery-order-and-accountable-gates)
requires a live frozen-brief review with conformance and quorum. §7.7 requires
interchangeable three-provider roles, and
[§24.4](mos-eisley-plan.md#244-evidence-gates) names all six assignments.
[Review-specific acceptance](REVIEW_CONFORMANCE_ACCEPTANCE.md) qualifies only its
exact three-attempt profile and explicitly denies broader conformance claims.

**Impact:** the order is stated, but the milestone boundary is not a single
enumerated acceptance matrix. An OpenAI-only success can be read as either G2's
completion or an intermediate component result. The required recorded versus
credentialed coverage of role permutations is not explicit. Historical API/evaluation
successes can be mistaken for completion of the conversational review path.

**Required plan correction:** publish a short G2 acceptance manifest naming intermediate
OpenAI component work, the complete product review path, supported role profiles,
and the evidence each needs. Bind the six recorded permutations and one three-family
live run to the manifest, with required failure/cancellation cases and spending
bounds. Keep component acceptance and full G2 completion separately named. Reuse
existing valid evidence only for the exact behavior it demonstrates. No further
product choice remains for this finding.

### A04 — Review rounds, corrections and format repair

**Decision, 2026-09-13:** resolved by Josh. One critic review followed by judge
adjudication is one review round. An author disputing a finding without changing
the artifact may submit one structured rebuttal; critic reconsideration and renewed
judge adjudication form the second and final round for that artifact. Changing the
artifact consumes one correction cycle and creates a newly frozen revision; at most
two correction cycles are permitted per task. Same-route response-format repair
consumes the shared time/spending budget but not a review round or correction cycle.
Uncertain provider delivery never permits an automatic retry. Trusted user
configuration may lower these numeric limits but may not raise them beyond the
product maxima.

**Evidence:** [§15.6](mos-eisley-plan.md#156-rounds) and
[loop phase L3](adversarial-review-loop-project-plan.md#phase-l3--evidence-triage-correction-and-final-review)
bound critique/rebuttal rounds per artifact and correction cycles per task at two.
[§7.5](mos-eisley-plan.md#75-escalation-on-signal) separately permits one same-route
format repair and a qualified capability escalation. §23.3 explicitly asks for a
defined rebuttal flow. Later text preserves counters and distinguishes failure
types, but does not supply a complete per-transition counting/disclosure table.

**Impact:** implementations can disagree about whether the initial review counts
as a round, whether a repaired response consumes another round, which counters a
plan/test revision consumes, and whether a critic sees an author's rebuttal or new
evidence. Shared dollar/time bounds help contain execution but do not make these
behaviors equivalent.

**Required plan correction:** specify each transition's input revision, recipient,
visible evidence, counter increments and permitted next state using the decision
above. The numeric bounds are maxima, so an accepted first pass stops. Name format
repair separately from transport retries and preserve the rule against resending
uncertain provider requests. New evidence that changes the material under judgment
creates a new frozen revision and consumes a correction cycle. Keep all cost within
the existing task ceiling. No further product choice remains for this finding.

### A05 — Compaction and changing user intent

**Decision, 2026-09-13:** resolved by Josh. A new message refines the active task
by default. It replaces only requirements with which it directly conflicts;
compatible requirements and unfinished work remain active. Status questions and
requests for explanation do not pause or replace the task. The complete objective
changes only when the user explicitly cancels or replaces it, or supplies a clearly
incompatible new objective. Compaction must preserve the merged intent and identify
the exact earlier instructions or constraints superseded by later ones.

**Evidence:** [§6.6.3](mos-eisley-plan.md#663-author-compaction-contract) says the
newest active user instruction wins over an earlier objective. §16.0 says new
messages refine the active task unless they explicitly replace or cancel it, and
a status question should not stop ongoing work.

**Impact:** the compaction wording can be implemented as wholesale objective
replacement, while the conversational contract calls for merging compatible
instructions. A request such as “check the status” during implementation could
erase the unfinished task in a summary. This is an ambiguity in the scope of
supersession, not a claim that any new instruction must be ignored.

**Required plan correction:** apply the decision above to both conversational state
and author compaction. Add examples covering status questions, corrections, budget
changes, explicit replacement and stop requests to the existing compaction acceptance
fixtures. No further product choice remains for this finding.

### A06 — Quality-study prerequisites for ordinary correction

**Decision, 2026-09-13:** resolved by Josh. Offline and recorded-fixture
implementation may proceed before G3. Production activation of ordinary
user-requested coding with the full author → critic → judge workflow requires G2,
execution/VCS containment, a small applicable G3 study showing acceptable quality,
damage and whole-task cost, and the E2 delegation evidence. Reduced review,
automatic cheaper-route selection and correction bypass additionally require their
G5/G6 evidence. G3 blocks production activation and quality claims; it does not
block implementation and testing.

**Evidence:** [G4](mos-eisley-plan.md#264-delivery-order-and-accountable-gates)
depends on an “applicable G3 quality gate.”
[Loop L4](adversarial-review-loop-project-plan.md#phase-l4--useful-measurements-and-independent-labels)
requires independent labels before correction bypass, review removal, route downgrade
or quality claims. [E2](mos-eisley-plan.md#245-post-gate-delivery-order) also has
delegation quality/cost qualification. Full judging remains required for initial L3
corrections, and inert development before activation is expressly allowed.

**Impact:** “applicable” does not identify which study receipt is required for a
user-authorized fix with full review, compared with automatic optimization or a
reduced-review policy. One implementation may block all useful coding pending a
research programme; another may incorrectly waive the E2/G3 evidence it actually
needs. The text does not establish an unavoidable dependency cycle.

**Required plan correction:** map each advertised mode to the decided prerequisites:
recorded fixtures, ordinary full-review correction, delegated production coding,
reduced review and automatic routing. State exactly which G3/E2 receipt each consumes.
Keep existing requirements until that mapping is implemented; research grading
cannot be replaced with a judge's opinion. No further product choice remains for
this finding.

### A07 — Encryption at rest

**Decision, 2026-09-13:** resolved by Josh. Local persistent storage requires
verified operating-system disk or volume encryption plus private file permissions.
Remote persistent storage requires TLS in transit, provider-managed encryption at
rest and enforced per-user access controls. Customer-managed keys and application-
level encryption are optional. When encryption cannot be verified, Mos blocks
persistent sensitive storage but may operate in an explicitly selected ephemeral
no-save mode.

**Evidence:** [§17.1](mos-eisley-plan.md#171-retained-artifacts-and-backend-selection)
requires encryption at rest for configurable persistence. §17.2 specifies private
directories and permissions locally and server-side ownership controls remotely.
The plan does not specify the accepted encryption mechanisms or their key/recovery
requirements; file permissions and encryption are different properties.

**Impact:** implementations can claim compliance using materially different
guarantees: operating-system disk encryption, application encryption, or a remote
storage provider's encryption. It is also unclear whether an unencrypted local
volume must block startup or be a separately disclosed profile.

**Required plan correction:** define the decided protections per backend, including
how platform/provider encryption is verified, what appears in preflight/status,
and how ephemeral no-save mode handles failures and shutdown. Document key, backup
and recovery responsibility for optional customer-managed or application-level
encryption. No further product choice remains for this finding.

### A08 — Release feature scope

**Decision, 2026-09-13:** resolved by Josh. Version 0.1.0 is the first complete,
stable core product. The current `0.1.0` package version is a development placeholder
until the release acceptance checklist passes. Its required scope is:

- G0–G6 and E1–E2, with their applicable acceptance evidence and dependencies.
- Terminal conversation, sessions, memory and context management.
- Claude, GPT and Gemini authentication and adapters.
- The author → critic → judge workflow, with a distinct model family per top-level
  role and difficulty-based, role-scoped subagents for all three roles; subagents
  may use any approved model family under the agreed isolation and budget rules.
- Sandboxed reading, editing, testing, Git and GitHub operations.
- An MCP client.
- Local storage and user-selected remote storage under the agreed storage policy.
- Verified installers and updates for macOS, Linux and WSL2.

G7 research, E3 multimedia/documents and E4 outward APIs are deferred beyond 0.1.0.
Native Windows remains planned for version 0.1.1. This decision records release
requirements; it does not claim that the features or gates are complete.

**Evidence:** [§27](mos-eisley-plan.md#27-windows-platform-release-contract)
binds WSL2 to 0.1.0 and native Windows to 0.1.1. §§28–29 require updates and easy
installation for the “finished product,” while explicitly keeping that work separate
from G2. G/E gates describe capability dependencies but do not provide one versioned
feature list defining 0.1.0's minimum complete product.

**Impact:** a recorded preview, a live review tool and the complete coding agent
could each be called the first release while meeting different subsets of the
written requirements. “Full native Windows parity” inherits that undefined feature
scope. This is a release-planning gap, not a reason to stop isolated G2 development.

**Required plan correction:** apply the accepted scope above to the versioned
release acceptance checklist and roadmap, preserving gate dependencies and the
WSL2/native Windows order. No further product choice remains for this finding.

### A09 — Current work-item authority

**Evidence:** the main plan directs readers to [the roadmap](ROADMAP.md) for current
status. Roadmap item 3 contains multiple historical “next” statements interspersed
with later implementations of those same boundaries. The main plan also has a long
chronological implementation history, while G0–G7 and E1–E4 remain broad gates.

**Impact:** “continue with the next item” does not resolve to one revision-bound
work item. An agent can revisit completed design, treat staged code as merged, or
advance infrastructure that does not close the product gate. This is the process
ambiguity directly exposed by the current conversation.

**Proposed resolution:** maintain one short current-work table with stable item IDs,
state, dependency, source requirement, branch/PR or commit, and exit evidence.
Identify the next ready item while listing other work and checks already in progress;
keep historical descriptions in a clearly marked history section. Link existing
designs instead of producing another role design.
Populate the table from verified code and CI state after this audit is resolved.

## Items not reopened

- Author/creator, critic and judge are model roles under the existing §7.7 and
  Josh's clarification. No new choice about recruiting human reviewers is needed.
- The original late-TUI milestone is explicitly superseded by §16.0 and the roadmap.
- Trusted policy versus project guidance, fresh-session privacy versus explicitly
  curated memory, and live replay versus recorded replay already have precedence
  or scope rules. Their earlier sketches are not new unresolved contradictions.
- G4 fixtures before production activation are explicitly permitted; a dependency
  cycle should not be inferred merely from later evidence gates.
- Model/rate tables are operational data subject to later freshness/provenance
  requirements. They were not treated as verified current provider facts here.
- A documented feature that is still unimplemented is not automatically a plan
  ambiguity. Findings above identify competing interpretations or missing criteria.

## Proposed disposition

Settle A01–A03 and identify the authoritative next item in A09 before resuming G2
implementation or spending on a new campaign. A01 mostly requires applying the
user's existing direction; A02–A03 require a concrete permission/acceptance contract.
Schedule A04–A08 before their respective feature gates rather than turning them
into new universal prerequisites. Keep the original plan unchanged until the
specific corrections are reviewed. No provider calls or production policy changes
were made for this audit.
