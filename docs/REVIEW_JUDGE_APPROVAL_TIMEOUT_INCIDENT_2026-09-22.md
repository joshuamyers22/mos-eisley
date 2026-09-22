# Incident Review: formal judge approval deadline expiry

- Date, duration, severity, owner: 2026-09-22; one formal-campaign slot; internal qualification severity 3; Joshua Myers.
- User, data, and business impact: critics completed, but the human judge-approval step expired before dispatch. No judge provider call occurred. The campaign did not qualify the corrected artifacts, and the unused judge allowance remained held in accounting.
- Detection, mitigation, and current risk: the approval flow failed closed at its signed deadline. The campaign was left terminal and unretried. The offline correction passes the complete repository gate; no further live call is authorized by this review, and a commit/image rebuild remain required.

| Time with timezone | Evidence/event | Decision/action |
|---|---|---|
| 2026-09-22 16:33:57 EDT | Formal controller judge-approval scope reached exclusive expiry after critic work and manual ceremony consumed the shared wall clock. | Stop; do not reuse or retry the terminal campaign. |
| 2026-09-22, later EDT | Offline inspection confirmed no judge transfer/result and a still-held deferred judge allowance. | Diagnose timing and accounting together. |
| 2026-09-22, later EDT | Red regressions reproduced lost execution time and unresolved graceful-terminal allowance. | Implement a formal-only fixed grace and exact source retirement. |

The trigger was a human approval arriving after the controller's single wall-clock
budget, not incomplete G1 work or a provider failure. Contributing conditions were
that critic execution and manual approval shared one 360-second window and that
terminal cleanup treated a known-unused spend-only allowance like possible provider
exposure. The deadline correctly prevented stale dispatch, but the timing contract
did not model a deliberate formal ceremony and the ledger lacked a narrow terminal
transition for a never-transferred allowance.

Systemic corrective actions owned by Joshua Myers are complete offline: bind a non-configurable
600-second formal approval grace into schema 2; preserve and resume only the active
execution remainder; clip the hard wall by envelope expiry; settle only the exact
still-held judge source on graceful terminal exit; retain critic, transferred and
uncertain exposure; improve inspection completeness; and add fault-focused tests,
operator documentation and a threat model. The focused suites and final repository
gate pass. A commit, production-image rebuild and wholly
fresh campaign remain separate later actions and require their normal authority.
