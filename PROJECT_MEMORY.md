# Project memory

This is a compact index of durable project facts. Source, tests, approved plans,
and runtime behavior remain authoritative.

| Key | Durable fact | Evidence | Last verified |
|---|---|---|---|
| `delivery.next.live-review` | G2's library integration and exact launch-admission gate are implemented. Production use next requires a real three-slot credentialed conformance campaign and signed production launch decision under one consistent operator mode. No public live-launch CLI exists. | `docs/ROADMAP.md`; `docs/REVIEW_CAMPAIGN_CEREMONY.md`; `docs/REVIEW_LAUNCH_ADMISSION.md` | 2026-09-19 |
| `workflow.template-guidance` | Material work uses a task-appropriate production-template guide and filled verification/threat-model records before implementation. | `AGENTS.md`; `docs/PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md` | 2026-09-19 |
| `provider.live-authority` | Offline previews, campaign seals, observer handoffs, evidence submissions, and conformance checks grant no dispatch authority. Live probes and launches require exact signatures, local approvals, current guidance, spending, runtime, and cleanup gates. Schema-1 `separated` mode requires disjoint human-role keys; ADR-0005 schema-2 `single_operator` mode permits one shared signer and explicitly accepts the absence of independent human review. | `docs/adr/0005-single-operator-review-authorization.md`; `docs/REVIEW_LAUNCH_ADMISSION.md`; `tests/test_review_launch_admission.py` | 2026-09-19 |

Do not add routine progress, transcripts, secrets, private data, or unsupported
inferences. Update an existing key rather than appending a duplicate fact.
