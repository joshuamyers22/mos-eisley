# Work Note: live read-only review qualification

- Status: ready for single-operator preparation; live execution not started
- Owner: Josh Myers
- Started (UTC): 2026-09-19
- Last updated (UTC): 2026-09-19
- Review or delete by: completion or cancellation of the production qualification
- Related issue/incident/ADR: `docs/ROADMAP.md` G2; `docs/adr/0003-openai-first-provider.md`

## Objective and completion evidence

- Intended outcome: qualify one exact live read-only critic/judge launch using the
  already-implemented campaign, observer, conformance, and launch-admission gates.
- Required invariants: one consistent schema-2 single-operator signer across custody,
  phase authorization, observation and launch review; three fixed credentialed
  attempts; complete dedicated-ledger accounting; an explicitly self-reviewed and
  signed exact launch decision; no retry, automatic release, scoring, or global activation.
- Evidence that will show completion: a freshly accepted three-slot campaign, exact
  pinned evidence and Joshua Myers signatures, matching launch-conformance output,
  schema-2 signed production launch admission, and preserved audit/spend/cleanup data.

## Context retrieved

- `PROJECT_BRIEF.md`, `docs/ROADMAP.md`
- `docs/REVIEW_CAMPAIGN_CEREMONY.md`, `docs/REVIEW_CAMPAIGN_RUNNER.md`
- `docs/REVIEW_OBSERVER_HANDOFF.md`, `docs/REVIEW_CAMPAIGN_SUBMISSION.md`
- `docs/REVIEW_LAUNCH_CONFORMANCE.md`, `docs/REVIEW_LAUNCH_ADMISSION.md`
- `docs/PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md`
- `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_VERIFICATION.md`
- `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_THREAT_MODEL.md`

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-19 | observation | GitHub `main` is `fa0faafb6f29421e46429001be3932b614f392f0`; it already includes brokered critic/judge flow, campaign sequencing/evidence, launch-conformance comparison, and exact signed launch admission. | GitHub ref plus roadmap and feature guides | Do not reimplement the older held-reservation boundary. |
| 2026-09-19 | decision | Treat remaining work as a high-risk production qualification ceremony and apply the current template's verification, threat-model, Python, work-note, and adversarial-review guidance. | Template survey and task records | Obtain the missing independent custody/reviewer roles and explicit paid-run authority. |
| 2026-09-19 | decision | Josh approved an aggregate provider-spend ceiling of USD 5.00 (`5,000,000` micro-USD) and nominated Ron Mexico for an independent role. No role separation, key custody, or credential access is inferred from the nomination. | User authorization in the active task | Assign Ron to one role and obtain a distinct launch reviewer or observer before preparing live authority. |
| 2026-09-19 | decision | Joshua Myers was nominated as launch reviewer, leaving Ron Mexico as campaign custodian/observer. These are nominations only; identity and disjoint key custody remain to be established. | User direction in the active task | Name a third, disjoint phase authorizer. |
| 2026-09-19 | decision | The owner proposed Joshua Myers also act as phase authorizer. The existing launch-admission contract rejects any launch reviewer sharing an identity or key with a phase authority or observer, so this configuration was not adopted. | `review_launch_admission.py`; `test_review_launch_admission.py` | Obtain a third person or explicitly revise the governance claim and its contracts before any live action. |
| 2026-09-19 | decision | Joshua Myers explicitly directed that one person—Joshua Myers—may perform every human role. ADR-0005 adopts schema-2 `single_operator`; the prior Ron Mexico nomination and third-person blocker are superseded for this campaign. | `docs/adr/0005-single-operator-review-authorization.md`; focused contract tests | Enroll one real Joshua Myers public key consistently; do not claim independent human review. |

## Handoff

- Current state: repository guidance is established; no credentials were read, no
  spending was reserved, no worker was started, and no provider request was made.
- Next smallest safe action: obtain Joshua Myers's actual public signing identity,
  provider credential custody, dedicated funded ledgers and immutable worker image;
  then freeze the exact schema-2 three-attempt bundle, paths and policy windows under
  the approved USD 5.00 ceiling.
- Required operational inputs: Joshua's public key (without persisting the private
  key), provider credential custody, funded dedicated ledgers, an immutable worker
  image, exact data-transfer review and current policy windows. Single-operator mode
  accepts self-approval risk and must never be described as independent human review.
- Checks already run: current GitHub refs and exact template/repository documents were
  inspected; copied-file hashes match the surveyed revision; referenced local documents
  exist; the focused contract tests and complete `make check` pass. The full gate ran
  2,437 source tests with four skips and 89% coverage, verified exports, built both
  distributions, and passed 1,839 installed-wheel tests. The first sandboxed full run
  could not bind local test sockets; the approved unrestricted rerun passed.

## Close and promote

- Outcome and verification: schema-2 `single_operator` permits Joshua Myers to hold
  every human review role; focused tests and `make check` pass.
- Durable fact promoted to `PROJECT_MEMORY.md`: schema-1 remains separated by default;
  schema-2 explicitly accepts the absence of independent human review.
- Decision promoted to ADR/documentation: `docs/adr/0005-single-operator-review-authorization.md`.
- Regression test, issue, or improvement-plan link: `tests/test_review_launch_admission.py`
  and `docs/SINGLE_OPERATOR_LAUNCH_CONTRACT_REVIEW.md`.
- Temporary artifacts removed: package smoke-test environments were automatically
  removed; normal `dist/` gate outputs remain ignored build artifacts.
