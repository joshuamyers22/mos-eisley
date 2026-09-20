# Project memory

This is a compact index of durable project facts. Source, tests, approved plans,
and runtime behavior remain authoritative.

| Key | Durable fact | Evidence | Last verified |
|---|---|---|---|
| `delivery.next.live-review` | G2's library integration, exact launch-admission gate, and inert one-process single-operator host are implemented, but production qualification ended unsuccessfully after three failed sealed campaigns and the authorized final-campaign exception is consumed. The response-budget and schema-2 content-bound citation defects are corrected. A separately authorized one-attempt retest at `81e9ff5` completed both schema-2 critics and its judge with a freshly reconstructed `accept` result, but both critics emitted zero findings, so positive live `source_unit` evidence was not exercised. Post-result observation construction failed and no signed observation exists. The run grants no qualification, retry, launch or routing authority; production live review remains unauthorized. | `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_VERIFICATION.md`; `docs/REVIEW_RESPONSE_BUDGET_FIX_VERIFICATION.md`; `docs/REVIEW_CITATION_FIDELITY_FIX_VERIFICATION.md`; `docs/LIVE_REVIEW_CITATION_RETEST_2026-09-20.md`; `notes/LIVE_READ_ONLY_REVIEW_QUALIFICATION.md` | 2026-09-20 |
| `workflow.template-guidance` | Material work uses a task-appropriate production-template guide and filled verification/threat-model records before implementation. | `AGENTS.md`; `docs/PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md` | 2026-09-19 |
| `provider.live-authority` | Offline previews, campaign seals, observer handoffs, evidence submissions, and conformance checks grant no dispatch authority. Live probes and launches require exact signatures, local approvals, current guidance, spending, runtime, and cleanup gates. Schema-1 `separated` mode requires disjoint human-role keys; ADR-0005 schema-2 `single_operator` mode permits one shared signer and explicitly accepts the absence of independent human review. | `docs/adr/0005-single-operator-review-authorization.md`; `docs/REVIEW_LAUNCH_ADMISSION.md`; `tests/test_review_launch_admission.py` | 2026-09-19 |

Do not add routine progress, transcripts, secrets, private data, or unsupported
inferences. Update an existing key rather than appending a duplicate fact.
