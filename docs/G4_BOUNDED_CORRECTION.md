# G4 bounded correction-cycle evidence gate

This sixth offline G4 slice records at most two correction cycles for one task. It
does not dispatch a coding child, edit Git, call a provider, approve an
implementation, or replace the required final whole-suite and independent review.
The purpose is to make a correction *eligible for a separately gated workflow*
only after a specific assertion failure is reproduced and adjudicated.

## Evidence and triage

The isolated worker now emits schema-2 observations with bounded failed-test IDs;
schema-1 receipts remain readable but cannot enter correction. Two distinct,
separately approved, one-use candidate dispatch receipts must name the same
authenticated provenance, binding, frozen package, image and collection. Their
exact failing IDs and collection/execution digests must agree, with positive
assertion failures, no import/runtime errors, and no unexpected successes. This
does not prove the oracle is correct or that a failure is an implementation defect.

An enrolled judge signs an exact triage record covering **every** failed test ID,
the two receipt hashes, a critic-review artifact hash, and a disposition. Each
`implementation_defect` must include an applicable-clause hash, citation-evidence
hash and violation-evidence hash. A test defect, plan gap, flake, infrastructure
error or unresolved finding cannot enter the correction cycle. The controller
verifies the judge key and signature but does not itself authenticate the critic
artifact or prove citation aptness or human independence. Those remain accountable
review obligations; in `single_operator` mode independence is expressly false.

## Bounded cycle

The creator signs a separate domain-separated cycle approval binding the exact
triage, task ID, cycle number, source revision, plan and creator-test hashes,
frozen package, child identity, owned paths, local-clock window, and maximum
input/output tokens, tool calls, seconds and micro-USD. The approval embeds a
fixed task deadline and aggregate *worst-case allowance*; the initial child
assignment and every correction grant consume that allowance. This is a
conservative allocation check, not proof of actual provider usage or settlement.

Admission replays both candidate claims and current Git, verifies signatures and
scope, then exclusively writes a private mode-`0600` claim in an existing
owner-owned mode-`0700` controller store. A duplicate or concurrent task/cycle
fails. A spent claim is never silently retried; a crash requires inspection. The
store, same-UID host and local clock are trusted. Moving to another store bypasses
this local replay boundary and is outside the contract.

To complete a cycle, present a fresh authenticated creator/reviewer/child/Git
chain and separately approved candidate receipt. The new creator approval must
start at the prior exact source revision. Approved plan and creator-test **claims**,
interfaces, rubric, reviewer test bytes, collection, adapter, dependency/build declarations and
child scope/budget are checked against the prior cycle. The package identity
changes only because the renewed creator approval reference changes. Completion
is itself an exclusive private record; a failed next candidate may enter cycle
two only after that stored completion and a new reproduction/adjudication. A
passing candidate is merely ready for final verification and review.

## Commands and remaining authority

`mos g4-admit-correction-cycle --help` and
`mos g4-complete-correction-cycle --help` list the exact artifact paths. Signing
keys are never accepted by either command; enrollment and signing occur outside
the CLI. All artifacts and both stores must remain outside the Git repository.
The completion command needs retained **prior** package and binding artifacts as
well as the new ones. Every output is canonical JSON written privately without
overwriting an existing path.

No G4 correction receipt grants child/provider dispatch or write authority.
The creator-test digest is an approval claim, not a Git blob comparison of all
creator test files; final whole-suite verification remains mandatory. Actual
correction execution, real key custody, authenticated critic quorum,
aggregate measured spend, final creator/reviewer whole-suite execution, independent
implementation review and creator acceptance remain separate gates. The clean
installed-wheel smoke for this slice passed 1,832 tests; that is not production
approval. See the [verification record](G4_BOUNDED_CORRECTION_VERIFICATION.md),
[threat model](G4_BOUNDED_CORRECTION_THREAT_MODEL.md), and [roadmap](ROADMAP.md).
