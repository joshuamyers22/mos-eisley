# Retained critic evidence and judge admission

Review broker clients now retain private `broker-response.json`,
`model-response.json` and `model-completion.json` records. Response storage begins
only after the isolated worker has acknowledged the reply and completed cleanup.
The completion receipt binds the complete canonical request, raw broker envelope
and decoded model response by SHA-256. Failed or cancelled attempts retain a
distinct receipt when storage remains available. A receipt does not establish that
the caller received the result or that a provider authenticated the record.

`verify_review_evidence` is a read-only reconstruction against a trusted
`ReviewSpendingEnvelope`, reviewer, ledger and explicit `ReviewPolicy`. It checks
the original envelope, every selected critic's request projection and broker audit,
terminal spending records, response hashes and raw-to-canonical decoding. It then
reuses the reviewer's strict critique parser and the pipeline's citation, provider
diversity, quorum and finding-deduplication rules. Exact duplicate findings collapse
to one sorted finding ID; distinct claims remain distinct. Critic identities remain
in retained provenance and are absent from the judge findings payload.

Missing, changed or partially written evidence blocks admission even when other
critics could satisfy quorum. A fully recorded failed, cancelled, invalid-JSON or
invalid-citation critic is excluded from voting; the remaining valid responses may
still satisfy the selected policy. Usable responses require settled spending.
Conservative uncertain charges remain charged. The default two-critic/two-provider
policy is unchanged; synthetic OpenAI-only fixtures explicitly select one provider.

`PreparedEvidenceJudgeTransfer` derives the judge request from those verified
findings. Its preview binds the whole evidence record, review policy and underlying
judge-transfer authorization. Issuance requires separate exact host confirmation,
reconstructs the evidence again, and rejects changes even when the resulting
findings happen to be unchanged. It then uses the existing atomic held-allowance
transfer and one-use broker, retaining `review-evidence.json` and
`review-evidence-approval.json` before returning the client. Failed persistence
after transfer leaves the destination held and does not permit a retry or refund.

`verify_evidence_judge_transfer` checks a trusted expected approval against retained
evidence, recomputes critic lineage and findings, and verifies the exact judge
request and spending/broker chain. Historical verification can run after expiry;
it grants no fresh provider authority. Actual issuance still enforces expiry,
pricing, approval, transfer and one-use rules. These are trusted-host integrity
records, not external provider attestations or final judge-verdict validation.

The lower-level `PreparedJudgeTransfer` remains a funding/request boundary. Live
review integration must use evidence-bound admission and still implement current
guidance admission, retained final-verdict verification and authorized credentialed
conformance. No live terminal mode or paid call is enabled by this library change.

Tests cover request and artifact substitution, raw/canonical disagreement, changed
outcomes, incomplete evidence, failures and cancellation, quorum and provider
diversity, duplicate/conflicting findings, byte budgets, storage failure, replay and
offline historical verification. The real Docker smoke runs synthetic critics and
a judge through evidence-bound admission and checks exact container cleanup.
Rollback preserves retained records and spending; no automatic repair or release
is introduced. See [judge transfer](DEFERRED_JUDGE_RESERVATION.md),
[spending envelopes](REVIEW_SPENDING_ENVELOPE.md) and [roadmap](ROADMAP.md).
