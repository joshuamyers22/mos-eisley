# G4 initial-candidate correction bridge work note

## Objective and authority

Connect two separately approved, matching failed `G4InitialCandidateReceipt` records to a bounded G4 correction eligibility gate without converting them to legacy `G4CandidateDispatchReceipt` records. The real dependency-ordering task supplies two such receipts on one unchanged signed integration. This work does not grant correction-child dispatch, provider spending, Git writes, final suites, or acceptance.

Starting controller revision: `fedd73c426e534c2a78ef19c2d22bf4dc29a0944`, clean. Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, and `templates/THREAT_MODEL.md`. Risk class: high, because this code admits a signed authorization chain. Sampling receipts and registries are outside scope.

## Invariants and decision evidence

| Blocking requirement | Evidence |
|---|---|
| Both initial receipts replay against their own signed claims, paid child, immutable integration, package, binding, controls, and clean Git | `verify_initial_candidate_receipt` for each run |
| The two runs are distinct, chronologically ordered, and fail with the same assertion IDs on identical source and test identities | Exact receipt and observation comparisons |
| Owner-signed triage covers every failed test; its judge roster and source policy match the initial chain | Correction policy and signature verification |
| Creator-signed cycle 1 stays inside the original assignment and aggregate task allowance | Exact budget and scope checks |
| A claim can be admitted once and grants no downstream write or dispatch | Private exclusive claim plus typed admission flags |

Ceiling: one minimal implementation pass, focused tests with forged and changed evidence, one full `make check`, and one real artifact replay. Stop on a stale source/package, absent owner signature, nonassertion error, mismatched failure ID, unresolved spend, or any unverified chain. Human owner approval is required for triage and cycle signing before a real claim is written.

## Threat model

Assets are the signed initial-child chain, frozen reviewer tests, private candidate claims, owner keys, and correction claim store. Untrusted inputs include child source and unsigned local artifacts. The bridge must not infer legacy provenance, mint signatures, copy provider payloads into review evidence, trust a receipt hash without replay, or treat agent-authored assessment as independent human review. Path, key, clock, claim-store, and same-UID tampering remain local trust assumptions; exact hashes and exclusive writes detect ordinary stale/replay attempts.

## Observed dependency-ordering failure and bridge result

The first signed initial candidate is `698af36b14877356c23dafb091666cef0ba04010fb3e0708c6f7bf559acc57ba`; the separately approved reproduction is `7fc888b9dd7ac2f447db61bf3030c6988d91612831153352017eb5d36ac43a05`. Both replayed against their signed paid-child and integration chain, each with the same sole failing assertion `test_order_reviewer.DependencyOrderReviewerTests.test_dependency_value_must_be_exact_string` and no errors. The signed integration resolves to commit `9bece145bdcd8047e19393fc39ae27f8ad09a45c`. The frozen plan requires invalid prerequisite entries to raise `ValueError`; the integrated implementation does not check exact `str` type for dependency values. The task-local critic review is at `/Users/josh/.mos-eisley-g4-distinct-deps-2026-09-30/deps12-correction-critic-review.md`.

`reviewer_initial_correction.py` adds a distinct admission type and replays both original receipt types before considering signed triage and a creator-signed cycle-one allowance. It uses the existing task/cycle claim namespace so it cannot be admitted twice or collide silently with a legacy correction claim. The resulting record has all dispatch, provider, Git-write, final-suite and acceptance flags false. Legacy correction-child dispatch does not accept this distinct type; any correction-child step needs a separate authority and implementation.

Focused tests cover the valid signed pair, duplicate claim, changed reviewer failure, changed test package, forged creator signature and excess allowance. The real receipt preflight passed with correction review policy SHA-256 `74045c239ace9f51d4196cb4e767de91bd8461db6170877344dec3a6d6ee31b0`.

The owner signed triage SHA-256 `67463c8c4f82fb3f51f32d14b2458d70d932e9edc6f64755ed770b43e551e090` and cycle approval SHA-256 `e59cbb73d9c3bf277daa411fc4281957f736357b69bd077a7e67a276db7c23df`. Both signatures and their exact task-local evidence were replayed. The one-use cycle-one claim was written outside Git, with admission SHA-256 `203aa25d5548e2e8d7fe855b79479f675852c502839b7c11ce80d4be90308710`. The private claim bytes match the canonical admission and have mode 0600. No correction child, provider call, Git write to task source, final suite or acceptance occurred.
