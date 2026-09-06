# Offline container-boundary adversarial review

Scope: isolated recorded evaluation only. No model-generated commands, paid calls,
live provider broker or automatic routing added.

| Failure or attack | Control/test | Remaining limitation |
| --- | --- | --- |
| Worker reads host labels or secrets | No mounts; stdin-only blinded job; host-file/env canary probes | Content already included in job/image and trusted daemon remain in scope |
| Image tag changes or creates implicit volumes | Local immutable ID, no runtime pull, volume metadata rejection | Image ID is not a trust signature |
| Network or privilege escalation | Network none, no capabilities, non-root, no-new-privileges; actual probes | Kernel/runtime escape not ruled out |
| Worker fills host memory/log storage | Incremental bounded stdout/stderr; Docker logs disabled | Daemon internals and host temporary input storage are trusted |
| Worker exhausts compute/processes | CPU/memory/PID/FD/tmpfs limits; cgroup checks | Host-side caller itself is not sandboxed |
| Attached client timeout leaves worker running | Exact-name force-removal in finally; real timeout/output probes | Hard host kill/daemon outage can prevent cleanup; watchdog still needed |
| Failed cleanup is silently accepted | Cleanup failure propagates as command failure | Manual ownership-aware investigation required |
| Worker invents a result | Strict parsing and exact comparison to recorded contract | Only useful for fixtures; a live broker needs different validation |
| Offline fixtures are mistaken for live measurements | Preserve recorded provenance and document boundary event | No signed historical containment attestation |

Actual Docker checks are now part of container CI. This milestone validates the
offline boundary without adding credentials/network to the worker. Next review
must address authenticated broker IPC, shared reservations and watchdog recovery
before any live sweep is enabled.
