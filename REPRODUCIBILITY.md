# Reproducibility

A clean checkout must reproduce installation, checks, tests, and build artifacts
using the committed runtime version and `uv.lock`:

```sh
make setup
make check
make audit
make build
```

Record external inputs, configuration, tool/runtime versions, and commands needed
to reproduce material results. Never depend silently on developer-machine state.

The authoritative dependency source is `uv.lock`; `requirements.runtime.txt` is
its hash-pinned runtime-only export. Update with `uv lock`, `make export-runtime`,
then run `make check audit container`. Frozen mode is used by all quality commands.

`mos replay RUN` verifies the exact artifact set and SHA-256 digests before parsing
the brief, policy, cassette and result. It recomputes the pipeline and compares the
entire result, not only the verdict. Serialization schema 1 is the replay contract.
New optional provider fields preserve legacy fixture request hashes, and agent replay
accepts schema-1 results recorded before full response capture; no general migration
or live re-execution is implemented. Retain the code revision and lock with exported
runs. An unsigned digest is integrity evidence, not authenticity.

The SQLite index is disposable metadata. Copy whole completed run directories for
backup; verify each with `mos replay` after restore. Do not back up a live SQLite
file by copying it; use SQLite backup facilities or rebuild its metadata from runs.
Inputs and recordings can contain proprietary source and must be stored privately.

`mos agent-replay RUN` separately verifies the canonical agent-loop artifact set,
including config, fixture values, request-bound cassette, journal and complete
result. It reruns the loop, compares every result and journal event, and requires
all recorded exchanges to be consumed. A manifest is written only after the live
journal is closed and the result is durable; partial runs are intentionally not
replayable or resumable.

`mos openai-run` is deliberately not reproducible as a model execution. It stores
the exact config, canonical response sequence, aggregate token usage and boundary
journal under a manifest. `load_live_run` verifies artifact hashes, provider/model
identity, initial-turn prefix, response count and journal response hashes. Retain
the code revision and lockfile with a live run. The API key is never an artifact.
There is no command that silently resends a stored live prompt.
