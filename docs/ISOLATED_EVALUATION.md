# Offline evaluation containment

`eval-run-isolated` runs the existing recorded evaluator in a constrained Docker
container. It accepts only a blinded batch and its exact request-bound cassette;
the labeled dataset, join map, grading references, spending ledger and credentials
are not passed to the worker. This is an offline containment/conformance milestone,
not live execution or new empirical model evidence.

Build the reviewed project image and inspect its immutable local ID:

```sh
make container
docker image inspect --format '{{.Id}}' mos-eisley:local
```

Use the returned `sha256:` ID and the absolute path of your trusted Docker client:

```sh
uv run --frozen mos eval-run-isolated \
  --batch batch.json --cassette cassette.json --output raw-results.json \
  --docker /usr/local/bin/docker --image sha256:<64-hex-image-id>
```

The placeholder intentionally requires replacement. Tags are rejected, runtime
pulls are disabled, and images declaring implicit volumes are rejected. Review the
image build inputs: an immutable image ID does not establish that its contents are
safe or free of private data. The project's build context excludes datasets and
local run artifacts. Docker, its selected daemon/context, the image and host caller
are trusted. The CLI does not install Docker or modify daemon configuration.

## Boundary

The host validates the fixture job, then sends canonical JSON over stdin. The worker
receives no host mount or inherited host API credential. Its root filesystem is
read-only, its UID/GID is 10001, capabilities are dropped, privilege escalation is
disabled and IPC is isolated. Limits are 512 MiB memory with no additional swap,
one CPU, 32 PIDs, 64 file descriptors and a 64 MiB noexec/nosuid/nodev temporary
filesystem. Docker logging is disabled to avoid a second unbounded output sink.
These controls use Docker's documented
[runtime options](https://docs.docker.com/reference/cli/docker/container/run).
The [none network](https://docs.docker.com/engine/network/drivers/none/) isolates
networking. Local Docker Desktop testing also exposed kernel-created inactive
tunnel devices; probes require all non-loopback interfaces to be down and test
egress denial. No provider endpoint is enabled through normal container networking.

Host stdin/stdout is capped at 16 MB, stderr at 64 KiB. Both output pipes are drained
incrementally so excessive output is rejected without first buffering an unbounded
body. Input uses a private temporary file on the host, never a mounted file. Provider
secrets are not copied into the Docker client's environment either; only explicit
Docker connection configuration and basic PATH/HOME are retained.

The attached execution deadline is 30 seconds. Image inspection, creation and exit
inspection have separate bounded deadlines; cleanup has a 10-second deadline.
Thus the whole command can take longer than 30 seconds. Failure/cancellation kills
the attached client and attempts force-removal of the specifically named container.
A cleanup failure is an error, never success. Container exit status and returned
contracts are checked, and recorded output must equal the host-computed fixture
result before any output artifact is created.

Results deliberately retain `recorded_fixture` provenance. The completion event
reports the image ID and `offline_container` boundary; this is not a signed
containment attestation. Existing grading/scoring works unchanged and must not
count these fixtures as credentialed model observations.

## Verification and limitations

`make container` now runs the actual constrained boundary, checks a host-only file
canary and credential canary are absent, rejects writes to the image filesystem,
checks UID/capabilities/no-new-privileges/seccomp and cgroup v2 resource settings,
and tests network denial, excessive output, timeout and cleanup. It also runs a
recorded fixture through the worker. CI runs these probes on Linux; local validation
also exercises Docker Desktop on macOS. Environments without the required cgroup
or seccomp behavior fail the smoke check. Unit tests cover malformed images,
implicit volumes, fixed launch flags, pipe limits, cleanup failures and wrong output.

This is not proof against container/kernel escape, a malicious Docker daemon,
host-side same-UID interference or information already included in a brief,
cassette or image. Temporary data can reach host swap/storage. Docker's virtual
filesystems still exist; no claim is made that every file is inaccessible. Resource
flags are verified in smoke tests, not dynamically attested before each request.
The caller controls the execution environment; production deployment must run the
probes against that same reviewed image and daemon configuration.

An abrupt host kill, machine failure or unreachable daemon can prevent cleanup and
leave an orphan, even though its CPU/memory/PID limits remain. There is no independent
watchdog yet. List candidates with `docker ps -a --filter name=mos-eval-` and inspect
ownership before removing an exact container; do not remove other runs by prefix.

Next: an authenticated, bounded request broker that holds credentials and the
shared spending ledger outside the worker, plus watchdog/cleanup recovery. Only
after that boundary and credentialed conformance pass should paid sweeps be enabled.
Automatic difficulty routing remains disabled pending held-out empirical gates.
