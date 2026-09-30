# G4 initial-candidate correction dispatch work note

## Objective and authority

Dispatch one real correction proposal for the dependency-ordering task after its signed initial-candidate cycle-one admission, using a separate creator dispatch approval and, if a provider is used, a separate short-lived live grant. Preserve the original paid child, integration, and two failed reviewer receipts. No task source, Git, final-suite or acceptance write follows from dispatch.

Starting controller revision: `d955261d99f21cc131485960963210fc82364409`. Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, and `templates/THREAT_MODEL.md`. Risk class: high because this is a one-use child and spending boundary. Sampling artifacts are outside scope.

## Invariants and acceptance evidence

| Blocking condition | Evidence |
|---|---|
| Exact initial correction admission and private cycle claim | Canonical admission and owner-private claim bytes |
| Both initial candidate failures and the paid child/integration chain still replay | `verify_initial_candidate_receipt` on each |
| Dispatch is bound to the signed cycle, current integrated source, frozen plan, creator tests, image, enrolled child and path | Distinct creator dispatch signature and deterministic exact offer |
| One attempt with no host source or Git write | Exclusive private dispatch claim, signed proposal, host and contained validation, clean Git replay |
| Provider use, if any, has separate exact live authority and settled spending | Signed production grant, shared ledger, measured production receipt |

The correction provider request now supports exact UTF-8 source output selected
by the signed request digest. Legacy base64 requests continue to replay under
their existing signed digests. The child broker encodes and hashes the returned
source before signing; neither format gives the provider a signing key.

## Dependency task handoff

Task root: `/Users/josh/.mos-eisley-g4-distinct-deps-2026-09-30`.
The frozen initial correction admission is
`203aa25d5548e2e8d7fe855b79479f675852c502839b7c11ce80d4be90308710`.
The exact dispatch signer is `/Users/josh/g4-deps12-correction-dispatch sign`;
the one-use live signer and call are `/Users/josh/g4-deps12-correction-live-sign`
and `/Users/josh/g4-deps12-correction-live-call`. The dispatch signer replays
both signed failed candidates, the admitted cycle and its private claim before
asking the owner to sign. The live signer binds the exact offer and UTF-8 source
request to the shared ledger. The live call claims dispatch before any provider
attempt and allows no retry. Each signer needs an owner-supplied key path; the
call needs an owner-supplied API key through a hidden prompt.

Focused correction and broker tests, Ruff and Pyright passed. `make check` in
the sandbox failed only because unrelated MCP tests could not bind loopback
sockets; the same check is being rerun with that permission.

## Dispatched evidence

The owner separately signed dispatch approval
`f689cdc5c147b32568dfab91d373065f933e7b0a2456ce1f5e8fc16218b334c4` and
live grant `52a285a2e965a7078a1091c440709cb16da2460e2d89732a868889e11216ea5b`.
Both bind the frozen offer
`f4282f4c49fa8bb8a940337574bef2e2fba70599338b45eff5b94c55728c2a1e`.
The one-use live call returned dispatch receipt
`320a37c5343e44fbdbb4a630e617a6051b370377e39274bf9cd7b1cafa092d1a` and
production receipt `04b9c5c9747e07c0649538cf5b704af6ae576c24b739175add98a835ee9d5dc9`.
Independent replay of the signed admission, dispatch, proposal, provider receipt
and ledger passed. The ledger is settled at 22,534 micro-USD, and the only
proposed changed path is `src/dependency_lab/order.py`, with zero unresolved
issues reported by the child. No source write, Git
integration, reviewer test or G4 acceptance was performed by this dispatch.

Stop on stale source or tests, changed claim, invalid signature, exhausted deadline or allowance, unresolved ledger spend, failed isolation, ambiguous provider response, or a consumed claim. Do not retry a spent child or provider grant.

## Threat model

Assets are the signed cycle admission and claim, provider key, child key, frozen package and test bytes, Git source, and ledger. Model output and task files are untrusted. The controller must keep source/test/plan text as data, bind the provider request to an exact offer, prevent claim replay, accept only signed scope-checked replacements, and retain measured spend. The same-UID host, Docker daemon/image, ledger, clock, creator and child key custody remain trusted. A single-operator owner signature does not claim independent human review.
