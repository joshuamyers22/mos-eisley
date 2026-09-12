# Approval and broker issuance for one review call

`run.review_broker.PreparedReviewCall` previews and issues one critic or judge call
through the existing isolated model client. Trusted host code supplies the reviewer,
role input, current spending policy and shared ledger. The reviewer now exposes pure
`critic_request` and `judge_request` methods; actual review uses those same methods.
There is no second prompt builder to drift from the approved request.

Preparation sends nothing, writes nothing and reserves nothing. It freezes the
canonical model request and original role input, and produces a `ReviewAuthorization`
in the distinct `read_only_review` mode. The confirmation hash binds the role, brief,
critic identity when applicable, exact role input, canonical and provider requests,
spending policy, full reservation, ledger identity/ceiling, unique entry ID and expiry.
The complete model request is available for host presentation alongside the policy
and reserved amount. A judge preview includes the exact supplied findings and their
IDs; it does not independently establish their pipeline lineage or quorum.

Issuance requires an explicit `approved_transfer_sha256` matching that preview. This
covers external token counting and generation for the exact request, including its
system instructions, review data and limits. The hash is a content confirmation,
not an authentication credential: trusted application code must obtain approval
through its user/admin policy boundary and must not automatically echo the preview
hash or accept approval from a model. Approval expires after at most ten minutes or
when pricing expires, whichever comes first. Each issued broker expires after at
most the requested timeout (up to 60 seconds) and before the approval expiry.

Review admission requires spending policy schema 2 with a conservative cache-write
rate. The full input-token ceiling and exact output-token cap are reserved at the
highest applicable rates; this amount must fit both the per-call limit and shared
ledger. A read-only preview checks available funds, but issuance repeats the ceiling
check in SQLite's serialized reservation transaction. Reservation occurs before
any bearer grant or provider operation. The unique ledger entry also burns the
approval across concurrent issuers using different artifact directories.

A new private directory retains the approval, canonical model request, role input,
optional critic identity, spending policy and planned reservation. The existing
`PreReservedOpenAITransport` consumes that exact held reservation without reserving
again. The broker binds its bearer to this review authorization, records admission
before counting, and records the host response or failure. Files contain private
review content and public hashes; bearer claims and provider credentials are not
written. The caller supplies a trusted filesystem parent and bounded, retry-free
provider transport. Credential acquisition and endpoint/conformance validation
remain responsibilities of the separately authorized host integration.

`verify_review_broker_audit` requires independently trusted expected authorization,
checks retained artifact hashes and the admission/outcome chain, and rejects
incomplete audits and downgraded outcome schemas. The existing research-assignment
reader still rejects review mode. A host `response_received` outcome is not evidence
that the model response parsed successfully, citations were valid or quorum passed.
These local audit records are not provider-authenticated evidence.

The durable reservation is intentionally conservative. Failed directory creation,
partial artifact writes, expiry after reservation, lost process state or an unused
issued grant leave funds held. A changed request cannot dispatch or refund its hold.
Cancellation or ambiguous dispatch retains the full uncertain amount. A valid
settlement retains actual cost even if the review parser later rejects the answer.
This boundary provides no repair, retry, automatic release or reissuance operation;
the trusted caller can inspect the ledger entry and retained files after interruption.

Synthetic tests cover exact projection through the reviewer, both roles, confirmation
mismatches, role confusion, pricing/cap/expiry changes, concurrent issuance, intervening
spending, partial preparation, artifact tampering, mode separation, replay, cancellation
and malformed answers. Real Docker smoke checks approval denial, a full pre-held
allowance, one brokered critic reply, verified audit, denied reissuance and exact cleanup.
No fixture is a credentialed conformance or production diversity claim.

This is a library integration for a single explicitly approved call. Live terminal
review remains gated on aggregate critic/judge envelope reservation, dynamic judge
admission with retained finding lineage, guidance checks, response/evidence retention
and authorized credentialed conformance. The existing pipeline still owns citation
validation, provider diversity, quorum and final verdicts. See the
[brokered client](BROKERED_MODEL_CLIENT.md), [model reviewer](MODEL_REVIEWER.md) and
[roadmap](ROADMAP.md). Rollback removes the new issuer; existing CLI commands, research
artifact schemas and spending-ledger schemas remain compatible. Retained holds must
not be erased during rollback.
