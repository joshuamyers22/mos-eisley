"""Private ephemeral Python workspace and fixed bounded creator-test runner."""

import asyncio
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from mos_eisley.coding_child import (
    CodeSnapshot,
    CodingBrief,
    CodingPatch,
    CodingTestExecution,
    CodingVerification,
    validate_pure_source,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.coding_child import (
    CodingAck,
    CodingExecution,
    CodingOffer,
    CodingWire,
    VerifyWire,
    replay_coding,
)

# Source/test subprocess gets no host environment, shell, mounts or network. Its
# entire process tree is additionally bounded by Docker and the host watchdog.
RUN_TESTS = """import importlib.util,json,sys,unittest
sys.path.insert(0,sys.argv[1])
loader=unittest.TestLoader()
suite=unittest.TestSuite()
valid=True
for index,path in enumerate(sys.argv[2:]):
    spec=importlib.util.spec_from_file_location("creator_test_"+str(index),sys.argv[1]+"/"+path)
    if spec is None or spec.loader is None:
        raise ValueError("Selected creator test cannot be loaded")
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    selected=loader.loadTestsFromModule(module)
    valid=valid and selected.countTestCases()>0
    suite.addTests(selected)
r=unittest.TextTestRunner(verbosity=1).run(suite)
passed=valid and r.wasSuccessful() and r.testsRun>0 and not r.skipped
print(json.dumps({"tests":r.testsRun,"skipped":len(r.skipped),"passed":passed,"files":sys.argv[2:],"failures":len(r.failures),"errors":len(r.errors)}))
sys.exit(0 if passed else 1)
"""


async def verify_snapshot(
    brief: CodingBrief, snapshot: CodeSnapshot, *, isolate_tests: bool = False
) -> CodingVerification:
    try:
        for source in snapshot.files:
            if source.path in brief.owned_paths:
                validate_pure_source(source.content)
    except ValueError:
        return CodingVerification(
            snapshot_sha256=snapshot.sha256,
            tests_sha256=brief.assignment.tests_sha256,
            passed=False,
            output_sha256=digest(b"Coding source policy denied execution."),
        )
    with TemporaryDirectory(prefix="coding-", dir="/tmp") as temporary:
        root = Path(temporary)
        if isolate_tests and os.getuid() != 0:
            raise ValueError("Coding verification needs its isolated supervisor.")
        root.chmod(0o755)
        for file in snapshot.files:
            path = root / file.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file.content)
            path.chmod(0o444)
        for directory in root.rglob("*"):
            if directory.is_dir():
                directory.chmod(0o755)

        async def execute() -> tuple[int, bytes]:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                "-B",
                "-c",
                RUN_TESTS,
                str(root),
                *brief.test_paths,
                cwd=root,
                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                user=10002 if isolate_tests else None,
                group=10002 if isolate_tests else None,
                extra_groups=() if isolate_tests else None,
            )

            output_bytes = 0

            async def drain(stream: asyncio.StreamReader | None) -> bytes:
                nonlocal output_bytes
                assert stream is not None
                output = bytearray()
                while block := await stream.read(4096):
                    output.extend(block)
                    output_bytes += len(block)
                    if output_bytes > 32_000:
                        raise ValueError("Creator tests exceeded their output cap.")
                return bytes(output)

            try:
                async with asyncio.timeout(brief.wall_seconds):
                    out, err = await asyncio.gather(
                        drain(process.stdout), drain(process.stderr)
                    )
                    code = await process.wait()
                return code, out + err
            finally:
                # Kill all descendants even if the direct test process exited.
                import signal
                from contextlib import suppress

                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()

        code, output = await execute()
        # Detect test or source tampering, added files and links after execution.
        files = tuple(
            sorted(p for p in root.rglob("*") if p.is_file() or p.is_symlink())
        )
        expected_paths = tuple(root / f.path for f in snapshot.files)
        unchanged = files == tuple(sorted(expected_paths)) and all(
            not p.is_symlink() and p.read_text() == f.content
            for p, f in zip(expected_paths, snapshot.files, strict=True)
        )
        execution = read_test_execution(output, code, unchanged)
        return CodingVerification(
            snapshot_sha256=snapshot.sha256,
            tests_sha256=brief.assignment.tests_sha256,
            passed=(
                code == 0
                and unchanged
                and execution is not None
                and execution.successful
                and execution.files == brief.test_paths
            ),
            output_sha256=digest(output),
            execution=execution,
        )


def read_test_execution(
    output: bytes, exit_code: int, files_unchanged: bool
) -> CodingTestExecution | None:
    try:
        # stdout precedes stderr, whose unittest summary may follow this receipt.
        records = [
            json.loads(line)
            for line in output.splitlines()
            if line.startswith(b'{"tests":')
        ]
        if len(records) != 1 or set(records[0]) != {
            "tests",
            "skipped",
            "passed",
            "files",
            "failures",
            "errors",
        }:
            return None
        record = records[0]
        return CodingTestExecution.model_validate_json(
            json.dumps(
                {
                    "files": record["files"],
                    "tests": record["tests"],
                    "skipped": record["skipped"],
                    "failures": record["failures"],
                    "errors": record["errors"],
                    "successful": record["passed"],
                    "exit_code": exit_code,
                    "files_unchanged": files_unchanged,
                    "output_bytes": len(output),
                }
            )
        )
    except (ValueError, TypeError, KeyError):
        return None


async def execute_wire(
    mode: str, payload: bytes, *, isolate_tests: bool = True
) -> bytes:
    if mode == "implement":
        wire = CodingWire.model_validate_json(payload)
        execution = await replay_coding(wire.job, wire.image_id)
        patch = CodingPatch.model_validate_json(execution.result.final_text)
        snapshot = patch.apply(wire.job.brief)
        result = CodingExecution(
            execution=execution,
            patch=patch,
            verification=await verify_snapshot(
                wire.job.brief, snapshot, isolate_tests=isolate_tests
            ),
        )
        return canonical_bytes(
            CodingAck(
                payload_sha256=digest(payload),
                execution_sha256=digest(canonical_bytes(result)),
                verification=result.verification,
            )
        )
    if mode == "verify":
        wire = VerifyWire.model_validate_json(payload)
        original = {f.path: f for f in wire.brief.verification_snapshot.files}
        if any(
            f.path not in wire.brief.owned_paths and f != original.get(f.path)
            for f in wire.snapshot.files
        ) or not set(wire.brief.test_paths) <= {f.path for f in wire.snapshot.files}:
            raise ValueError("Protected creator test package changed.")
        return canonical_bytes(
            await verify_snapshot(
                wire.brief, wire.snapshot, isolate_tests=isolate_tests
            )
        )
    raise ValueError("Unknown coding operation.")


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("One fixed worker operation required.")
        raw = sys.stdin.buffer.readline(1026)
        if not raw.endswith(b"\n") or len(raw) > 1025:
            raise ValueError("Invalid offer size.")
        offer = CodingOffer.model_validate_json(raw)
        sys.stdout.buffer.write(canonical_bytes(offer) + b"\n")
        sys.stdout.buffer.flush()
        payload = sys.stdin.buffer.readline(256_002)
        if (
            not payload.endswith(b"\n")
            or len(payload) > 256_001
            or digest(payload[:-1]) != offer.payload_sha256
        ):
            raise ValueError("Invalid coding wire.")
        result = asyncio.run(execute_wire(sys.argv[1], payload[:-1]))
        if len(result) > 256_000:
            raise ValueError("Coding result exceeded its bound.")
        sys.stdout.buffer.write(result + b"\n")
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        print("Coding worker validation/execution failed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
