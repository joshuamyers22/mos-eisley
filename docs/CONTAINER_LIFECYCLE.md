# Independent container cleanup

The offline evaluation launcher now arms a detached host watchdog before starting
its worker. The watchdog is outside the container, has no prompt or provider key,
and only receives a validated full container ID, a bounded lifetime and a private
lease pipe. This is cleanup recovery for the existing offline boundary, not a live
credential broker or authorization to execute arbitrary model-selected commands.

## Lifecycle

1. Create the stopped container; require Docker's full 64-hex ID.
2. Create a private lifecycle directory and immutable `lease.json`.
3. Spawn the watchdog in a new session, passing only its lease reader. The launcher
   keeps a non-inheritable writer; Docker clients and workers do not receive it.
4. Watchdog persists `armed.json` and acknowledges readiness. No readiness within
   five seconds means the worker is not started and the launcher attempts cleanup.
5. Start and monitor the worker using its full ID, never a reusable name.
6. Launcher cleanup removes its exact container and closes the lease. The watchdog
   independently removes it on lease EOF (including launcher death), an unexpected
   lease byte, or its monotonic deadline, whichever arrives first.
7. Persist `result.json`. Normal completion requires a successful watchdog exit and
   a `removed` receipt matching both the container ID and lease hash.

The separate session and explicit file-descriptor passing use documented
[Python subprocess controls](https://docs.python.org/3.12/library/subprocess.html).
Cleanup uses Docker's exact-ID
[force removal](https://docs.docker.com/reference/cli/docker/container/rm/).
If removal fails because another cleanup already won the race, only a successful
empty exact-ID listing proves absence. A daemon error is never treated as absence.
There is no prefix-wide removal, prune, name reuse or caller-supplied shell command.

## Bounds and records

The watchdog lifetime is the attached execution timeout plus five seconds (default
35 seconds, maximum 65), beginning just before readiness. It cannot be extended by
the launcher. Cleanup tries at most three times, with a 200 ms pause between failed
attempts. Each removal and absence check has its own three-second deadline and
bounded output. A live launcher waits up to 25 seconds for watchdog completion;
it reports failure instead of killing a slow guardian. Initial OS process creation,
filesystem stalls and host suspension are not hard-real-time bounded.

By default, records live under `.mos-eisley/container-lifecycles/<random-id>/`.
Override the root with `eval-run-isolated --lifecycle-root PATH`. The completion
event includes `lifecycle_path`. Root ancestors are trusted; new directories use
0700 and files 0600. The records contain hashes, container identity, configured
lifetime, state and attempt count—not prompts, API keys, raw Docker diagnostics
or account credentials. These records are unsigned local evidence, not an
authenticated remote attestation. They accumulate until deliberately archived or
removed by the operator; the launcher never automatically erases failed evidence.

`armed` means the guardian initialized, not that the worker started or finished.
`removed` confirms cleanup, not successful evaluation or a spend refund.
`cleanup_failed`, missing or malformed receipts require investigation. Disk failure
can prevent a receipt even after successful removal. Lifecycle and spending
records are independent; uncertain model charges must not be released merely
because a container was removed.

## Verified and excluded failures

Container CI starts a sleeping worker, waits until Docker confirms it is running,
then SIGKILLs its launcher. The detached watchdog must remove that exact worker,
record success and leave no new evaluation container behind. Tests also cover a
live lease writer that cannot extend the deadline, bounded cleanup retries,
readiness failure, malformed IDs, receipt mismatch, and redundant launcher cleanup.
The watchdog does not rely on Python finally/atexit in the killed launcher.

Remaining limitations:

- A host shutdown or a killed watchdog can defeat independent cleanup. The launcher
  still has its own cleanup path while alive; this is not a boot-persistent service.
- A crash between container creation and watchdog arming can leave a stopped
  container. This path never starts a worker without the readiness handshake.
- An unreachable daemon, exhausted retry budget, disk failure or unavailable
  runtime can leave an orphan. No infinite retry or silent success is used.
- Docker executable/context/configuration and the same-UID host user are trusted.
  Do not switch daemon context or connection configuration during a run; there is
  no durable, independently authenticated daemon binding or cross-host recovery.
- A hostile worker escaping the kernel/container boundary is outside these
  guarantees. It normally cannot reach the host lease descriptor or guardian.
- Container metadata and local receipts are not a single atomic transaction.
  The full ID avoids targeting another container after a name is reused, but it
  does not make Docker operations transactional with local disk writes.

For unresolved cleanup, inspect the private lease and the current daemon before
removing that exact container. Do not infer ownership from a name prefix alone.
Paid empirical evaluation remains disabled pending the authenticated, bounded
provider/spending broker and credentialed conformance.
