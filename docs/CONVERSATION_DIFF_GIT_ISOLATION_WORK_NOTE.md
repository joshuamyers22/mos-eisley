# `/diff` Git process isolation

Status: implementation complete; Linux x86_64 CI and accountable owner security review pending. Owner: Josh Myers. Started: 2026-10-03 UTC.

## Objective and scope

Close the first hardening condition in the [owner security review](CONVERSATION_DIFF_OWNER_SECURITY_REVIEW.md): every `/diff` Git read must run in an OS-enforced process boundary that denies network access and repository-selected helper processes. A concurrent rewrite of `.git/config` and `.gitattributes` must not execute a marker helper. Keep the existing selected-workspace, path, size, deadline, stale-snapshot and Git-executable checks. Unavailable isolation refuses the read, including for a non-Git directory. No provider, Git write, release, or expanded workspace authority is added.

Selected guidance: [Python engineering](PYTHON_ENGINEERING_GUIDE.md), [bounded verification](AGENTIC_VERIFICATION_GUIDE.md), [verification template](../templates/AGENTIC_VERIFICATION_LOOP.md), [adversarial review guide](ADVERSARIAL_REVIEW_PLAYBOOK.md) and [review template](../templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md), [threat-model template](../templates/THREAT_MODEL.md), [ADR template](../templates/ADR.md), and [work-note template](../templates/WORK_NOTE.md). The existing [diff threat model](CONVERSATION_DIFF_PANEL_THREAT_MODEL.md) and [Git foundation](CONVERSATION_DIFF_GIT_FOUNDATION.md) define the boundary. The [process-isolation ADR](adr/0015-diff-git-process-isolation.md) records the durable decision.

Risk class: material security boundary. Budget: three correction passes, one focused integration pass and one final `make check`. Stop on an unavailable OS mechanism or a failing helper/network negative test; report the unsupported host instead of falling back to plain Git. Accountable owner review remains required before broadening the accepted local trust scope or release.

| Blocking dimension | Evidence | Pass rule |
|---|---|---|
| OS process and network denial | Real child-launch and loopback probes on each qualified host | Both fail inside the boundary; Git read works |
| Concurrent config rewrite | Real checkout with scan/read barrier and malicious filter helper | Marker never executes; changed read refuses |
| Fail-closed and regression | Non-Git unavailable-boundary test, existing Git and `/diff` tests | No silent empty view, stale or partial result |
| Packaging and quality | Installed-wheel test, lint, strict typing, `make check` | All applicable gates pass without skipping a required host claim |

## Evidence and handoff

The implementation wraps every Git call in macOS Seatbelt or a Linux launcher with inherited seccomp and `no_new_privs`; it probes the boundary before non-Git classification and refuses unsupported hosts. The launcher starts from Python isolated mode, and the parent closes unrelated file descriptors. A same-process exploit in the trusted Git binary and same-user replacement of trusted code remain outside this boundary.

Adversarial review traced the `/diff` snapshot and patch calls through the single bounded process adapter, checked the unavailable-boundary failure path, and challenged the race test with an unsandboxed positive control. The first control could not execute because the Linux test mount disallowed execution; the fixture was corrected before counting the result. The later test targets the actual patch argv and demonstrates both execution without confinement and denial with confinement. The [threat model](CONVERSATION_DIFF_GIT_ISOLATION_THREAT_MODEL.md) records the remaining trust assumptions; this self-review is not the accountable owner security decision.

- macOS real-checkout and isolation suite: 16 tests passed, including a concurrent `.git/config`/`.gitattributes` rewrite whose new helper did not execute. The strengthened race targets the patch command; replaying its exact Git arguments without the OS boundary executed the marker helper. A real child-process attempt and loopback network attempt were denied by the OS.
- Existing `/diff` panel and acceptance suites: 5 and 4 tests passed.
- Linux aarch64 no-network, read-only container: all 16 real-checkout and isolation tests passed. The temporary fixture mount allowed execution so the unsandboxed positive control could prove the helper was runnable; the confined read still prevented it. The strengthened patch-command race passed separately. Child creation and loopback networking were denied. Linux x86_64 qualification remains pending.
- The final macOS `MOS_REQUIRE_TMUX=1 make check` passed: Ruff, format, strict Pyright, 2,720 source tests (4 skipped), coverage reporting, export verification, wheel build, and 1,978 installed-wheel smoke tests. The wheel selection includes both real Git and OS-isolation test files. Linux x86_64 CI remains pending.
