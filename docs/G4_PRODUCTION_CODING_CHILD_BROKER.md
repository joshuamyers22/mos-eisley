# G4 separately authorized production coding-child broker

This is a callable, provider-capable G4 correction-child boundary, not a CLI or a
live campaign. Implementing and testing it made **no** provider call. The offline
correction-child dispatch grant remains insufficient for provider use. A creator
must additionally sign an exact, short-lived production grant binding the frozen
offer, provider request, model/effort, enrolled child, provenance policy, spending
policy, ledger, and immutable container image. The trusted composition root must
provide the enrolled child private key, OpenAI transport, existing private ledger,
and run directory outside Git. Neither a model response nor a repository file may
mint these dependencies.

`preview_correction_child_offer` replays the same read-only source and approval
preflight used at dispatch, producing exact offer bytes before the operator signs
the production grant. The preview grants no dispatch or spending authority; the
actual dispatch repeats the preflight and rejects changed source or test bytes.

`coding_child_request` creates one stateless, tool-free Responses request with the
complete frozen offer. Its text is task data; it carries no ambient repository,
network, credential, or tool authority. The provider returns an untrusted JSON
proposal over existing owned paths. A live proposal is generated only after the
separate signed production grant, current cycle/dispatch links, exact request hash,
conservative cache-write-priced reservation, policy validity, and private-store
checks pass. The shared ledger reserves before broker issuance; its entry ID is
the signed production grant's digest, so a second process cannot redeem the same
grant. The existing private one-use correction-dispatch claim is independent and
must also be consumed by `dispatch_correction_child`.

The existing no-network, no-mount worker exchanges a single-use request-bound
broker claim with the host. Only the trusted host holds the transport and child
signing key. It counts input and sends one non-streaming response under the
pre-reserved spending controller; no automatic retry is allowed. Provider-reported
token usage is checked against the reservation and settled into the shared ledger.
Uncertain sends retain the full hold; a pricing/budget violation blocks the ledger.
An invalid or refused model answer can still cost money but cannot create a signed
proposal. Only a parsed, completed, valid, scope-checked proposal is signed by the
enrolled child runtime. The old `dispatch_correction_child` host and isolated-worker
checks still govern its acceptance as a correction proposal; the production broker
does not write source or Git.

The private run directory retains exact approval, offer, audit, provider response,
spend reservation/receipt, and successful production-broker receipt. The verifier
reconstructs request/pricing identity, ledger settlement, audit chain, provider
output and the exact signed proposal in the separately validated dispatch receipt.
Measured spend here means provider usage reconciled under the local pricing policy;
it is not an independent invoice or proof of upstream billing. The same-UID host,
transport construction, signing-key custody, Docker daemon/image, ledger files and
clock remain trusted. A crash after reservation is fail-closed and needs inspection;
it does not authorize retry or release.

This boundary grants no execution of corrected code, creator/reviewer whole-suite
result, renewed custody/Git/candidate chain, critic quorum, merge/push or final
acceptance. Those gates remain open. See the [threat model](G4_PRODUCTION_CODING_CHILD_BROKER_THREAT_MODEL.md),
[verification record](G4_PRODUCTION_CODING_CHILD_BROKER_VERIFICATION.md), and
[roadmap](ROADMAP.md).
