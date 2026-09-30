# Conversation live review boundary

- System: v1 terminal conversation `/review`, selected `review-live` launch.
- Owner and accountable reviewer: Joshua Myers; owner review remains required for
  release and live spending. Engineering review here is not that approval.
- Trigger: a conversation invokes a live review of one prepared brief.
- Scope: selection, frozen conversation state, child process, completion receipt,
  cancellation and resume. Existing campaign, provider and signer gates retain
  their own threat models.

| Asset | Need | Boundary and control |
|---|---|---|
| Provider keys and signer authority | Confidentiality and one-use authority | Private paths stay in the launch selection, outside saved conversation state; `review-live` performs signed admission. |
| Brief and campaign identity | Exact binding | Selection bytes, config, prepared brief, campaign seal and evidence hashes are checked before queue and dispatch. |
| Spend ledger and retained result | No silent retry or false completion | Child owns one attempt; success needs a private exclusive completion receipt and matching retained-result hash. Cancellation consumes the attempt. |
| Workspace and session | Owner isolation | Selection workspace must equal current workspace; resume supplies current selection and policy again. |

## Abuse cases and residual risk

| Case | Control | Evidence | Residual risk |
|---|---|---|---|
| Saved session replays a provider call | No paths or keys in packet; current runner and policy required; completed/cancelled attempts do not restart | `tests/test_conversation_live_review.py` | An operator must protect private manifest and credential files. |
| Manifest, brief or evidence is swapped | Hash and exact-brief checks at queue and dispatch; `review-live` repeats its own admission | `tests/test_conversation_live_review.py`; `tests/test_review_launch_admission.py` | Local filesystem races remain subject to the existing live-launch boundary. |
| Child exits after partial work or completion file is forged | Fresh output paths, child status, exclusive receipt and retained-result digest/brief checks | `tests/test_conversation_live_review.py` | A compromised local owner process can edit private files; this is outside the single-owner host model. |
| Cancellation leaves active provider work | Send interrupt, await child; terminate and kill on bounded escalation; no retry | `tests/test_conversation_live_review.py` | Provider-side work already accepted may settle after local interruption; ledger and run must be inspected. |
| Unqualified image or brief is treated as G2-qualified | Existing campaign scope and signed launch bind the exact image/profile; operator docs require new qualification | `docs/CONVERSATION_LIVE_REVIEW.md`; `docs/G2_OWNER_OPERATED_CONTRACT.md` | Exact candidate live validation and owner release approval remain open. |

Decision: keep authority in the established `review-live` process and retain only
non-secret hashes in conversation state. No general provider activation or
production decision follows from this integration.
