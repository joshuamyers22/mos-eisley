# Production-template survey for live read-only review

## Source and scope

- Repository: `https://github.com/joshuamyers22/production-project-template`
- Reviewed ref: GitHub `main`
- Reviewed commit: `8879be48f3b760e65f6bed32f8740314fe92910d`
- Commit date: 2026-09-16
- Prior Mos Eisley review: `d59f3e661a1fa3456505cf36f91b51f4a1c873ac`
- Survey date: 2026-09-19
- Scope: current repository standard, agent working agreement, Python guide,
  bounded verification guide/template, adversarial review guide/template, work-note
  template, threat-model template, and release checklist.

The upstream revision was inspected from a detached temporary clone. No upstream
code or dependency was installed. This document records guidance provenance; it
does not claim that the template or Mos Eisley is production-ready.

## Selected source identities

| Source | SHA-256 |
|---|---|
| `AGENTS.md` | `902132acc9c37998a0e6f77518592280a7e695eab3d66b056485b7cf83fcf801` |
| `standards/PRODUCTION_REPOSITORY_STANDARD.md` | `9549d30b491c466aacb8152242f1caf1e7a68761bd6a74387bf56d100d1809c5` |
| `docs/AGENTIC_VERIFICATION_GUIDE.md` | `f0ea5eba1e0a90fb8263252d3d3779a3b70645e99f2e07d2e6095a5d04932ca2` |
| `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md` | `786d0e89ad56621f3a5f9399d8a66f75385fcb235383b00674373652f54bb01e` |
| `docs/PYTHON_ENGINEERING_GUIDE.md` | `9b6ae36bc08a34f0100dce2d4cf2947f110fc5114773070505d12539015d6f9e` |
| `templates/AGENTIC_VERIFICATION_LOOP.md` | `426a11484eb026b45e2c51e6cb69a16f58768627dad7a9b5502a7de0ee5fc17f` |
| `templates/WORK_NOTE.md` | `ddaa662dde003c1feeb19d1df4a8abe47db2ea394054ad439b76f355fb49f332` |
| `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md` | `340c54d3b0373bc70ebac07038d38e304cc3b9f54e643c59c77e4cf80698bd1e` |
| `templates/THREAT_MODEL.md` | `13ea1f25274d80f2faf4540e35c71c65e3b04fb5584349d86412c0fd3bd453c0` |
| `checklists/RELEASE_READINESS.md` | `6927107685e8c376bf97fad04af00377fe9931ac6d4ca460fec1aec74df31883` |

## Findings and adoption

The template has advanced since Mos Eisley's earlier pinned review. The intervening
commits add Git/GitHub identity controls and specialized scientific, PostgreSQL,
MCP, and optimization guidance. Those domain additions do not change this live
provider boundary. The material change for this task is the current repository
standard's explicit agent-work baseline: retrieve project context, select a guide,
define a bounded evidence-changing loop, keep a work note for multi-session work,
and require accountable review for security and financial authority.

For the live read-only review execution boundary, adopt:

- `docs/PYTHON_ENGINEERING_GUIDE.md` for immutable contracts, injected clocks and
  transports, bounded I/O, cancellation, specific exceptions, and negative tests;
- `docs/AGENTIC_VERIFICATION_GUIDE.md` with a filled verification record for the
  high-risk authorization and spending change;
- the threat-model template for credential exposure, replay, duplicate dispatch,
  stale authorization, ledger substitution, partial failure, and cancellation;
- the adversarial playbook and report template after the coherent implementation
  slice, with exact commands and evidence;
- the repository's existing `CONTRIBUTING.md` batching rule: focused boundary tests
  after each slice and one complete `make check` before publication.

The copied guides/templates are exact at the recorded hashes, except `AGENTS.md`,
which is adapted to Mos Eisley's existing plans and gates. Specialized guides are
used only when their domain applies; using a template never grants runtime authority
or substitutes for executable evidence.
