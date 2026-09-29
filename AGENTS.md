# Mos Eisley agent working agreement

Human instructions in the current task take precedence. Repository requirements,
tests, runtime behavior, and approved decisions remain authoritative.

## Retrieve and select guidance before acting

1. Read `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, the applicable plan or
   ADR, and the relevant implementation and tests before a substantial change.
2. Select the smallest applicable repository template or guide before changing
   code. Record that selection in the task note or verification record.
3. Treat `PROJECT_MEMORY.md` as an evidence-linked index, never as evidence by
   itself. Correct it when it conflicts with source or tests.

Use this routing table:

| Work | Required guide or template |
|---|---|
| Material Python implementation | `docs/PYTHON_ENGINEERING_GUIDE.md` |
| Multi-pass, security, correctness, or production-readiness work | `docs/AGENTIC_VERIFICATION_GUIDE.md` and `templates/AGENTIC_VERIFICATION_LOOP.md` |
| Credentials, authorization, spending, private data, or a new trust boundary | `templates/THREAT_MODEL.md` |
| Architecture or adversarial code review | `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md` and `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md` |
| Multi-session work, handoff, experiment, or material investigation | `templates/WORK_NOTE.md` |
| Durable architectural decision | `templates/ADR.md` |
| Incident or production failure | `templates/INCIDENT_REVIEW.md` |

## Work and verification

- Define the objective, invariants, non-goals, acceptance evidence, risk class,
  resource ceiling, and stopping rules before extended material work.
- Implement the smallest coherent slice and run focused tests immediately.
- Test affected identity, storage, permissions, credentials, authorization, and
  spending boundaries before dependent work.
- Each additional verification pass must add evidence or a meaningfully different
  authorized perspective. Never count repeated introspection as verification.
- Run `make check` once for the combined batch before publication. Re-run affected
  checks after later code changes and never report a skipped check as passing.
- Security, governance, financial logic, and release approval require accountable
  review beyond an agent's own assessment.

## Branch naming

- Use a concise branch name that describes its current work, such as
  `feat/<capability>`, `fix/<defect>`, or `docs/<topic>`. Do not keep an
  origin-task name after the branch grows into a different workstream.
- Before renaming a published branch, check open pull requests, protections,
  automation references, and other worktrees. Preserve its commits and update
  the local upstream; do not rename unrelated or worktree-owned branches as part
  of a single-branch task.

## Notes and memory

- Keep disposable output outside Git. A tracked work note records concise facts,
  evidence, decisions, and handoff state—not hidden reasoning, prompts, secrets,
  raw provider payloads, or unrestricted command output.
- Promote only durable, project-specific facts to `PROJECT_MEMORY.md`, keyed and
  linked to source, tests, or an ADR. Update facts in place and remove stale items.
- Repository files must never contain API keys, bearer capabilities, private signing
  keys, client data, or provider credentials.

## Template provenance

The selected guides and templates are pinned from
`joshuamyers22/production-project-template` commit
`8879be48f3b760e65f6bed32f8740314fe92910d`. See
`docs/PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md` for scope and applicability.
