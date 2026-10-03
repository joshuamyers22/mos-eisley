# Bounded file-reader platform contract

This is the first narrow extraction under [plan §27.2](mos-eisley-plan.md#272-version-011--full-native-windows-support).
It does not implement native Windows file reading or qualify the complete CLI.

`mos_eisley.run.files.read_bounded(path: Path, limit: int = 2_000_000) -> bytes`
retains its signature and delegates to `mos_eisley.platform.files.read_regular_file`.
The boundary validates the limit, selects the current platform explicitly and
imports only the selected adapter when called. Imports perform no file I/O.

A limit must be a nonnegative integer; booleans, negative values and nonintegers
raise `ValueError` before opening. This is an intentional input tightening.
Zero accepts an empty regular file and refuses nonempty content. Reads return
unchanged bytes, request at most `limit + 1` bytes and refuse overflow rather than
truncate. Limits are caller-selected; this primitive does not impose an additional
application-wide maximum.

On macOS and Linux, admission uses `O_NOFOLLOW | O_NONBLOCK | O_RDONLY`, then
checks the opened descriptor's regular-file type. Final-component symlinks fail
with `OSError`; FIFOs fail without waiting for a writer. Missing files and open or
stream errors propagate as `OSError`; nonregular descriptors and overflow raise
`ValueError`. Directory opens retain the existing `IsADirectoryError` from stream
wrapping. Owned descriptors close on success and failure, including wrapping
failure (a previously unhandled leak).

On native Windows and other unqualified platforms, valid requests raise
`UnsupportedPlatformError`, an `OSError` subclass, before importing the POSIX
adapter or opening any input. There is no permissive fallback. The isolated wrapper
and contract import without POSIX constants. Other CLI imports remain coupled to
POSIX; this extraction does not promise native CLI importability.

This primitive does not enforce ownership, private permissions, ancestor-path
containment, hardlink rejection or immutable content. Ancestor symlinks and
hardlinks remain allowed. Higher-level storage/security boundaries retain those
responsibilities. A future Windows adapter must establish its handle/reparse and
regular-object guarantees before the selector can admit it; separate storage
contracts still need SID/DACL, identity, locking and durability qualification.

## Verification

[Isolated tests](../tests/test_platform_files.py) characterize the original valid
POSIX behavior, test final-path substitution, FIFO refusal with a subprocess
deadline, read caps, descriptor cleanup and unsupported import/refusal.
They run in the source suite and the existing installed-wheel smoke suite.

`uv run --frozen python tools/smoke_platform_files.py` exercises just this contract
from a fresh wheel-only environment outside the checkout. No runtime dependencies
are necessary for these standard-library-only modules. The helper verifies the
module comes from the new environment and removes inherited `PYTHONPATH`.

CI's `windows-files` job runs that helper with `--require-native-windows` on
`windows-latest`, selecting the four common reader import/validation/selection tests
and ten portable identity value/import/refusal tests without POSIX skips. The flag refuses execution on another platform; this job is
required by the aggregate `quality` check alongside the Ubuntu source/wheel gates.
Actual Windows evidence remains pending until CI runs on a published branch.
Local simulated refusal is supplementary evidence, not native qualification.

[Work and boundary record](BOUNDED_READER_WORK_NOTE.md) records verification and
remaining qualification work. No native support or release claim follows from this
contract extraction.
