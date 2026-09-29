# ADR-0005: Explicit single-operator review authorization

- Status: accepted
- Date and owner: 2026-09-19, Joshua Myers

## Context and options

The schema-1 live-review contract requires phase authorizers, observers, and launch
reviewers to have distinct identities and public keys. The intended production
qualification has one accountable human available: Joshua Myers. Using several keys
held by Joshua would not create independent judgment, and relabeling self-review as
independent would make the evidence misleading.

The options were to keep live review blocked, remove role checks globally, or add an
explicit trust mode. The owner directed that Joshua Myers be allowed to perform every
human role. The USD 5.00 aggregate provider-spend approval remains a separate,
task-specific ceiling; this decision does not create credential access or dispatch.

## Decision and consequences

Add schema-2 `operator_mode: "single_operator"` policies and evidence. This mode
requires exactly one shared signer identity and public key across campaign phase
authorization, observation, target-phase authorization, and launch review. Mixed
single-operator and separated-role chains fail closed. Joshua Myers is the intended
production operator; reusable code validates the signed identity rather than embedding
a person's name.

Schema 1 remains the default `separated` mode and retains disjoint identity/key checks
and canonical bytes. A schema-2 launch decision cannot claim that an independent
observer assessment occurred. It must instead sign
`single_operator_self_review_risk_accepted: true`.

The change preserves three precommitted attempts, model critic/judge context
separation, exact scope hashes, local approvals, spending ceilings, credential-order
gates, immutable runtime bindings, evidence reconstruction, revocation, no retry, and
cleanup requirements. It removes only independent human custody and review. A
compromised or mistaken Joshua can therefore authorize, attest, and approve the same
bad evidence without another human detecting it. Signatures prove artifact integrity
and accountable self-approval, not independence or correctness.

The mode is reversible by issuing a new schema-1 separated policy chain. Existing
schema-1 artifacts remain valid under their original contract. This ADR does not run a
live campaign, generate a private key, select a credential, or activate a public CLI.

## Verification

Acceptance requires tests showing one `joshua-myers` signer can complete the full
synthetic campaign and launch path, schema 1 still rejects role reuse, mixed modes are
rejected, and schema 2 records self-review risk without an independence assertion.
Reconsider this decision before broader activation, automatic routing, higher spending,
multi-user use, or whenever an independent reviewer becomes available.
