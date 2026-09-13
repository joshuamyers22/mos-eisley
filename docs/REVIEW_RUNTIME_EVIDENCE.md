# Review runtime evidence

The owned [review probe](REVIEW_CONFORMANCE_PROBE.md) now writes private host records
around each token-count and generation operation. A read-only collector links those
records to the exact approved request, retained provider response and worker cleanup
receipt, producing the evidence pins and time intervals used by
[observer records](REVIEW_CONFORMANCE_OBSERVATION.md).

These are host measurements for independent inspection. They do not authenticate
the remote provider or replace an independent observer's assessment of the runtime.
No observer signature, live conformance result or launch permission is generated
automatically.

## Captured records

Each critic directory and the judge directory may contain four additional files:

- `runtime-count-start.json` and `runtime-count-end.json`.
- `runtime-generation-start.json` and `runtime-generation-end.json`.

Construction and declined approval write none of these files. After credential
admission and transport construction, a start record is written before calling the
SDK. The probe repeats current admission checks after that write. Failure to write
the start prevents the provider operation. A start therefore means an operation was
being attempted; it cannot prove that bytes reached a remote endpoint.

Start records bind canonical model-request, phase-authorization and provider-payload
hashes, SDK version, selected image, UTC time and the active worker's cleanup lease.
End records bind the start hash, UTC completion time, monotonic duration and a
returned/failed/cancelled status. Returned records include a result hash; counts also
include the returned integer. Exceptions are represented only by status, with no
exception text. Records contain no key, request prose or response prose.

Files use exclusive creation and mode 0600 in the already private call directory.
Missing, partial or failed records are not repaired into success. A failed end write
stops completion and preserves conservative spending. Recording failure during an
existing error or cancellation does not replace that original exception. Cleanup
still belongs to the controller and is awaited before the owning call returns.

Recorded intervals include SDK execution, client closure and surrounding local
checks. They are conservative host intervals, not server-side latency measurements.
Records rejected before transport construction need not have runtime files; their
existing controller/broker/spending state remains authoritative.

## Cleanup linkage and collection

`probe.lifecycle_paths` captures the host-selected lifecycle directory for each
critic, followed by the judge. Capture preserves earlier paths even when a container
object is reused sequentially. A missing path stays `None`. The caller should retain
these trusted outputs independently of artifacts being inspected.

For each stopped call, pass its call directory, independently selected lifecycle
directory, exact `ModelRequest` and verified phase authorization to
`collect_review_runtime_exchange`. The collector:

- Bounds regular-file reads and rejects symlinked evidence directories/files.
- Checks operation/start/end hashes, exact count and generation payloads, runtime
  bindings, signed validity windows and the 60-second duration ceiling.
- Checks token-count consistency and matches the generation result hash to the
  retained broker response.
- Requires both operations to identify the same cleanup lease/container, and a
  matching watchdog result with state `removed` and at least one removal attempt.

Its `ReviewObservedExchange` contains hashes of two canonical bundles: the four
transport records and the lease/removal records. It includes the measured intervals
without exporting provider response content. The original files remain available
for independent inspection. `verify_review_runtime_exchange` rereads them and checks
equality with an independently pinned observer exchange, detecting later changes.

The collector requires trusted, stopped directories; it is not an atomic snapshot
of an active writer. It checks the supplied authorization's bindings and time window,
but does not authenticate its signature or reconstruct the entire review itself.
Use the existing observation builder/authenticator for the independent signatures,
controller, complete spending and verdict chain. Validate runtime evidence pins
alongside that authentication; the generic observer format also supports other
independently collected evidence and does not automatically load these files.

## Limits and validation

Cleanup receipts, SDK metadata, clocks and transport hashes remain local host
records. They cannot prove provider authorship, historical policy continuity or
honest host execution. An independent observer must inspect actual runtime and
matching evidence before signing. Repeated-probe acceptance and explicitly
authorized live runs remain outstanding; live launch remains unavailable.

Focused tests cover collection, tampering, wrong-worker cleanup, missing evidence,
write failures, private records, provider errors and cancellation. Real Docker smoke
tests collect both phases into a fixture observer record and verify cancelled-worker
cleanup, using only synthetic provider responses and test signing keys.
