# `/diff` Git process isolation threat model

## Scope and ownership

Owner: Josh Myers. Trigger: first hardening condition in the accountable `/diff` security review. Scope: selected local Git checkout, Git process launch, repository configuration and attributes, and the resulting bounded snapshot/patch. Provider requests, staging, edits, and release remain outside this change.

## Assets, actors, and boundaries

An adversary controlling repository files may rewrite `.git/config` and `.gitattributes` while a read is running, or make a Git filter/diff helper point at an executable. The owner-selected Git binary and installed Mos Eisley code are trusted. Git output and repository metadata are untrusted. The host kernel and OS sandbox facility are trusted for process and network enforcement.

| Abuse | Impact | Required control and evidence | Residual limit |
|---|---|---|---|
| Config changes after the helper-key scan | Helper command executes as the owner | macOS denies child creation and other executable paths; Linux denies child creation and `execveat` before Git starts. Concurrent rewrite test uses a marker helper. | Linux permits the launcher's initial `execve`, which the filter retains across; a hypothetical same-process Git exec is not a covered helper path. Same-user modification of trusted application or Git bytes remains outside the boundary. |
| Helper attempts network access | Local data exfiltration | Deny network system calls in the Git process; real loopback negative probe | Git still reads the selected repository and returns bounded patch data to the owner |
| OS isolation is unavailable or fails | Plain Git runs after a silent fallback | Probe isolation before classifying non-Git; fail visibly and never retry unsandboxed | Platform support is limited to hosts where the enforced boundary works |
| Git child or helper survives timeout | Continued work after view cancellation | Deny child creation; retain process deadline and bounded output | A single bounded Git process can run until its deadline |
| Git config or attributes change during a read | Stale or misleading display | Retain pre/post config and snapshot checks; refuse on detected change | The read is not an atomic filesystem transaction |

## Decisions

The existing fixed Git arguments, helper overrides, byte caps and path admission remain defense in depth. The OS boundary is mandatory for every Git call and is probed before any non-Git result is returned. The process boundary denies helpers and network; it does not by itself deny file writes or protect a compromised Git binary. No credential, provider, Git mutation or release authority follows. Accountable owner review is required before broadening the prior trusted-local acceptance.
