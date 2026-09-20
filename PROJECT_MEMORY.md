# Project memory

This is a compact index of durable project facts. Source, tests, approved plans,
and runtime behavior remain authoritative.

| Key | Durable fact | Evidence | Last verified |
|---|---|---|---|
| `delivery.next.live-review` | G2's library integration, exact launch-admission gate, and inert one-process single-operator host are implemented, but production qualification ended unsuccessfully after three failed sealed campaigns and the authorized final-campaign exception is consumed. The response-budget defect is corrected offline with independently sealed 8,000-byte visible-text and 64,000-byte canonical-envelope limits. The citation-fidelity defect is also corrected offline: opt-in critic-request schema 2 uses deterministic content-bound raw/before/after diff units, while schema 1 remains byte-compatible and raw-only. Neither correction changes failed receipts or revives qualification. Production live review remains unauthorized; no replacement campaign or public live-launch CLI is authorized. | `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_VERIFICATION.md`; `docs/REVIEW_RESPONSE_BUDGET_FIX_VERIFICATION.md`; `docs/REVIEW_CITATION_FIDELITY_FIX_VERIFICATION.md`; `notes/LIVE_READ_ONLY_REVIEW_QUALIFICATION.md` | 2026-09-20 |
| `workflow.template-guidance` | Material work uses a task-appropriate production-template guide and filled verification/threat-model records before implementation. | `AGENTS.md`; `docs/PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md` | 2026-09-19 |
| `provider.live-authority` | Offline previews, campaign seals, observer handoffs, evidence submissions, and conformance checks grant no dispatch authority. Live probes and launches require exact signatures, local approvals, current guidance, spending, runtime, and cleanup gates. Schema-1 `separated` mode requires disjoint human-role keys; ADR-0005 schema-2 `single_operator` mode permits one shared signer and explicitly accepts the absence of independent human review. | `docs/adr/0005-single-operator-review-authorization.md`; `docs/REVIEW_LAUNCH_ADMISSION.md`; `tests/test_review_launch_admission.py` | 2026-09-19 |

Do not add routine progress, transcripts, secrets, private data, or unsupported
inferences. Update an existing key rather than appending a duplicate fact.
