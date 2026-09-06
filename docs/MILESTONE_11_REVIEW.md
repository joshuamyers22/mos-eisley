# Container lifecycle adversarial review

Scope: independent cleanup for offline evaluation, with bounded private lifecycle
records. No paid request, live evaluation broker, automatic routing or broader
machine capability was added.

| Failure or attack | Implemented control | Residual boundary |
| --- | --- | --- |
| Launcher is SIGKILLed and cannot run finally | Detached watchdog observes lease EOF; real Docker crash test | Host/watchdog death and daemon failure remain possible |
| Launcher hangs while retaining lease | Independent monotonic deadline, no extension protocol | OS/host scheduling is not hard-real-time |
| Worker inherits lease and keeps itself alive | Non-inheritable writer; explicit reader passed only to guardian | Host-side same-UID processes are trusted |
| Guardian never initializes | Readiness handshake gates worker start | A stopped container can remain if all cleanup also fails |
| Guardian dies after readiness | Launcher retains its own exact-ID cleanup path | Simultaneous launcher/guardian loss is not covered |
| Container name is reused | Start, inspect and post-create cleanup use validated full ID | Creation-response failure still uses this invocation's random name |
| Removal races another successful cleanup | Exact-ID absence requires successful daemon response | Changing daemon context can undermine the observation |
| Daemon outage is mistaken for absence | Bounded retries and explicit cleanup_failed state | No persistent recovery service after retry exhaustion |
| Receipt is stale, for another lease or claims success after failure | Bind full ID/lease hash and require clean guardian exit | Same-UID tampering and cross-resource atomicity are not solved |
| Container removal is mistaken for refunded spend | Lifecycle and financial outcomes remain separate | Provider reconciliation still required for uncertainty |

Next: authenticated provider/spending broker across the isolated boundary, with
bounded messages and explicit credentialed conformance before any paid sweep.
