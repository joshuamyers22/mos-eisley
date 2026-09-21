# Project memory

This is a compact index of durable project facts. Source, tests, approved plans,
and runtime behavior remain authoritative.

| Key | Durable fact | Evidence | Last verified |
|---|---|---|---|
| `delivery.next.live-review` | G2's library integration, exact launch-admission gate and inert one-process single-operator host are implemented. A fresh standalone campaign at `b3357aa` now supplies positive live V-007 evidence: three strict-schema critics ran, one `invalid_evidence` slot was tolerated by the two-of-three quorum without retry, the judge returned `accept`, Joshua signed the four-exchange observation, the complete standalone bundle replayed successfully, all 24,032 micro-USD settled locally and all workers were removed. This does not rewrite the earlier terminal campaigns or satisfy the stricter three-precommitted-slot production-qualification rubric; Q-001, a fresh formal campaign, launch conformance and a separate launch decision remain open. No qualification, retry, launch or routing authority follows. | `docs/LIVE_REVIEW_DEADLINE_RETEST_2026-09-21.md`; `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_VERIFICATION.md`; `docs/REVIEW_STRUCTURED_OUTPUT_QUORUM_FIX_VERIFICATION.md`; `docs/STANDALONE_REVIEW_EVIDENCE.md` | 2026-09-21 |
| `workflow.template-guidance` | Material work uses a task-appropriate production-template guide and filled verification/threat-model records before implementation. | `AGENTS.md`; `docs/PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md` | 2026-09-19 |
| `provider.live-authority` | Offline previews, campaign seals, observer handoffs, evidence submissions, and conformance checks grant no dispatch authority. Live probes and launches require exact signatures, local approvals, current guidance, spending, runtime, and cleanup gates. Schema-1 `separated` mode requires disjoint human-role keys; ADR-0005 schema-2 `single_operator` mode permits one shared signer and explicitly accepts the absence of independent human review. | `docs/adr/0005-single-operator-review-authorization.md`; `docs/REVIEW_LAUNCH_ADMISSION.md`; `tests/test_review_launch_admission.py` | 2026-09-19 |

Do not add routine progress, transcripts, secrets, private data, or unsupported
inferences. Update an existing key rather than appending a duplicate fact.
