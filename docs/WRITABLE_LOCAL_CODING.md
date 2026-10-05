# Writable recorded local coding

This extends [local background qualification](LOCAL_BACKGROUND_QUALIFICATION.md)
with an explicitly connected, unpaid coding route. The qualified source profile is
`pure_python_v1`: bounded Python function modules using approved value operations.
It can implement meaningful algorithms such as boundary validation and clamping.
It does not activate general Python, shell commands, paid providers, automatic
spawning, or the default delegation policy. The E2 quality/efficiency study and
matched creator-only comparison remain pending.

## Creator workflow

The creator first writes a plan, interfaces, acceptance criteria and concrete
executable tests. A `CodingBrief` freezes the plan and test digests, exact Git base,
allowlisted source snapshot, owned file paths, immutable test paths, route and
resource allowance. Existing owned files cannot be omitted and overwritten as new
files. New source files require explicit ownership. Tests are included before
implementation; children cannot replace, delete, or weaken them.

A trusted host critic/judge adapter returns an accepted `CodingReview` of that exact
plan/test package. The host creator authorizer must then supply a finite-lived
`LocalChildAuthorization` with mode `recorded_coding`, exact brief/assignment/review
identities, and current owner/session/workspace observation. These are separately
installed trusted adapters. A receipt from a child, repository file or model output
cannot install them or grant authority. Their callbacks must be bounded, side-effect
free observations of explicit approvals; reconnecting them does not approve work.

`ConversationController.run_coding_child(brief, cassette, expected_revision=...)`
reserves parent input/output and one task attempt, then durably records both the
implementation job and a required integration job before dispatch. One explicitly
request-bound recorded response produces a structured `CodingPatch`. It contains
only owned file replacements/additions with exact previous-content digests. Empty,
unchanged, duplicate, stale, protected and escaping paths fail closed. The child
gets the brief and selected files, never parent history, ambient repository files,
provider credentials, a Git executable or host VCS authority.

The worker applies that patch to a private ephemeral snapshot and runs the frozen
creator tests. The host independently replays the exact unpaid response, parses the
same patch, and validates the digest-only worker acknowledgement against the pinned
image, execution journal, request, usage, snapshot and tests. The existing broker's
1 KiB response boundary remains intact. Source/patch text stays in the host-held
recording and handoff rather than being trusted as new worker output.

The VCS broker stages the patch in an isolated detached worktree and returns a
bounded deterministic diff. The creator can review `record.coding.handoff` and the
existing `/agent` inspection interface. Failed tests retain a report and block
integration. A completed child report explicitly does not approve integration;
its required integration job remains unpassed until the full workflow finishes.

`integrate_coding_child(child_id, expected_revision=...)` requires accepted final
critic/judge review of the exact patch plus a separate finite-lived
`CodingIntegrationApproval` binding owner, session, child, handoff and final review.
It reserves another aggregate task attempt, durably records integration in progress,
and reruns the complete frozen test package in a fresh container. Only then can the
broker make its one-use staging commit and fast-forward the clean exact parent.
The controller retains the known applied commit before a further fresh verification
of the actual integrated source snapshot. Only that final passing receipt makes the
required integration job pass. Review rejection, changed approvals, tests, source,
revision or scope prevent publication.

The host adapters are explicit constructor dependencies: `coding_authorizer`,
`coding_reviewer`, `coding_executor`, `coding_broker`, and
`coding_integration_authorizer`. All five must be supplied together. There is no
model-selected spawning or terminal shortcut to creator approval. The same session
header, JSON/SQLite stores, goal ledger and shutdown ownership retain these children;
no second child or scheduling registry is introduced. Inspection may mark a report
stale after the workspace changes, including approved integration: its original
assignment observation no longer represents the current tree. The exact integration
and final verification receipts remain in the retained coding record.

## Containment and resource limits

The local route uses an immutable Docker image, stdin-only transfer, no host mounts,
no network, read-only image filesystem, private bounded tmpfs, no credentials,
32-process/512 MiB/one-CPU cgroup limits and detached watchdog cleanup. A trusted
supervisor has only SETUID/SETGID for launching tests and KILL for exact process-group
cleanup. It runs the test process
under a separate unprivileged UID. Source and creator tests are supervisor-owned
read-only files. Generated source is never executed as the supervisor, so it cannot
rewrite those files or use the supervisor's result pipe. These supervisor
capabilities are confined to this container profile; the earlier read-only profile
continues to drop all capabilities and use its original unprivileged UID.

`pure_python_v1` restricts source syntax and calls before execution. It rejects
imports, runtime introspection, unapproved builtins/calls, attribute writes, hooks,
nonlocal/global state, executable default values and noninert annotations. It is a
capability restriction alongside Docker, not a general Python sandbox or a proof of
correctness. Frozen creator tests still need adequate independent review.

Source/test snapshots have at most 32 files and 128 KiB canonical size, each file
at most 64,000 characters. There are at most 16 owned paths and 16 test paths,
10,000 source syntax nodes, depth one, four retained children and one active child
per session. Each child has one unpaid model exchange, no retries or corrections,
and an explicit one-to-20-second operation allowance. Parent cumulative byte,
attempt, cost and goal wall-time ceilings apply; reservations never refund on failure.
Trusted test execution has bounded stdout/stderr, loads each selected test file directly (including nested files), rejects empty
selected files, skips and an early successful exit without a completed-run receipt, and kills its exact process
group on timeout/cancellation. Docker teardown owns the remaining container tree.

VCS operations run off the event loop through an owned serialized operation with one
absolute deadline and caller-created cancellation event. Cancellation can interrupt
Git commands, waits for their exact process cleanup, and then records uncertainty.
It cannot promise to reverse a commit already applied before cancellation or a lost
acknowledgement. Such work remains retained for explicit host reconciliation and
cannot be replayed automatically.

The Git broker requires exclusively host-controlled workspace/staging directories,
a clean exact base, regular tracked source files and an allowlisted bounded checkout.
It disables hooks, fsmonitor, external diffs, signing, credentials, fetching and
ambient Git environment/configuration. Attributes, filters/includes, symlinks,
gitlinks, hidden/sparse index entries and ambient ignored/untracked files are
rejected. This narrow clean repository profile must be selected explicitly; it is
not an assertion that every existing repository supports writable delegation.
Cleanup removes only this broker's registered unchanged worktrees. Modified,
interrupted or uncertain staged commits are preserved for host inspection.

## Cancellation, restart and qualification evidence

Goal pause/cancel/clear and terminal stop/exit propagate to the exact owned coding
operation and await cleanup. Cancellation or lost acknowledgement retains the full
reservation, adds uncertainty once and pauses a working/waiting goal without
reopening a cancelled goal. A cold restart converts running implementation or
integration to uncertainty; it never retries writes, drops charges or assumes a
commit did not happen. Completed reports, protected tests, patches/diffs, review
receipts, known applied commit and final verification survive both stores.

Focused suites cover VCS isolation, stale/escaping/protected patches, hooks/filters,
cancellation before/during/queued Git work, aggregate deadlines, lost commit
acknowledgements, creator ordering, revoked approvals, parent reservations, failed
tests, required integration jobs, persistence failure, both stores and restart.
Worker controls cover a known-bad baseline, changed/empty/skipped tests, test-runtime
attack attempts, selected nested-file omissions, early zero exit, output/time bounds and forged acknowledgements.

`make container` runs `tools/smoke_coding_child.py` against the actual local Docker
image: creator tests precede a meaningful clamping implementation, the known-bad
baseline fails, the child stages a patch, missing creator integration approval blocks
publication, accepted exact final review/approval permit integration, fresh tests
verify the actual parent tree, both stores retain results, and cancellation of a
second real worker preserves the parent and aggregate charges. The complete batch
also requires `make check`, including fresh installed-wheel tests.

Evidence currently applies to the local macOS Docker host. Linux CI, Windows/WSL2,
other source/tool profiles, arbitrary repositories, paid/live providers, external
ingress, automatic delegation and statistical default-policy promotion retain their
separate qualification gates in plan §§14.2–14.2.1 and E2.
