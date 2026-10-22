# Scriptable execution boundary

Owner: Joshua Myers. Reviewed engineering scope: baseline `b0490655`, 2026-10-21.
Review again when adding implementation commands, automatic resume, new tools,
new transport or result-schema changes. This record is technical analysis, not
independent security or release approval.

Assets are private conversation state, exact review evidence, provider credentials,
aggregate spending and the integrity of downstream CI decisions. The operator
selects arguments and optional stdin; project text, recordings, model output and
child diagnostics are untrusted data. Entry points are the existing console
script, bounded stdin, selected recording/review files and existing live manifests.
The renderer must not become a second policy or credential owner.

| Abuse/failure | Control | Evidence / residual limit |
|---|---|---|
| Oversized, malformed or ambiguous input | Read at most 8,001 bytes, strict UTF-8, byte/line bounds; validate before startup | Source/wheel invalid and exact Unicode-boundary tests; an open producer can wait until interrupted |
| Piped slash text executes controls | Submit one literal message; review requires an explicit option and frozen packet | Literal `/review` test; no REPL/composer or shell |
| JSON stdout contamination or terminal escapes | Versioned JSON encoding, plain renderer escaping, diagnostics on stderr, live child stdout redirected | Source/wheel plain/JSON tests; closed stdout cannot receive results |
| CI treats revise/reject or absent quorum as acceptance | Explicit task/review statuses and verdict; incomplete review exits 5 | Complete and incomplete recorded reviews; consumers must check the verdict |
| Credential/authority bypass | Reuse chat composition and exact live-review selection checks; reject interactive implementation options | Denied live startup tests plus existing live chat/review regressions; no new paid qualification claimed |
| Replay or budget reset after failure/cancellation | Shared controller/store and ledgers, consumed attempt persistence, no retry/resume loop | Failure, cancellation and existing-ledger limit tests on source/wheel |
| Lost persistence acknowledgement yields false result | Disclose uncertain persistence, suppress answer/usage/evidence claims | Fault injection and existing store recovery tests; explicit inspection required |
| Repeated signals orphan work | Cancel the owning task once, await controller/transport cleanup | Real signal and asynchronous cleanup tests; SIGKILL/host loss remains an uncertain crash |
| Exceptions expose inputs or credentials | Fixed diagnostics except for locally constructed input guidance; no raw exception serialization | Invalid-argument and unexpected-failure tests |

Dependencies and package provenance remain the existing hash-locked wheel and
release pipeline. No new dependency, network destination, publication capability,
automatic tool authority or credential storage is introduced. Existing recovery,
revocation and uncertain-spend procedures remain authoritative. Actual credentialed
live operation and release decisions remain Joshua's responsibility; this change
does not waive their existing gates.
