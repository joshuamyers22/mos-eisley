"""Bounded redacted observation of the unchanged staged-version smoke contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import selectors
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import cast
from unittest.mock import patch

from mos_eisley import app_install
from mos_eisley.app_release import ReleaseError, platform_id
from tools import smoke_app_distribution
from tools.qualify_rc16_discovery import SOURCE, VERSION, admitted

OUTPUT_LIMIT = 8192


def process_state(pid: int) -> dict[str, object]:
    """Query one owned process; never persist identifiers, arguments or paths."""
    try:
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "stat=,pcpu=,time=,rss="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        fields = result.stdout.split()
        if result.returncode or len(fields) != 4:
            return {"state": "unavailable"}
        state = fields[0][0]
        cpu = float(fields[1])
        parts = [float(v) for v in fields[2].split(":")]
        seconds = sum(v * 60**i for i, v in enumerate(reversed(parts)))
        rss = int(fields[3])
        if state not in "RSDIZTUX" or not all(
            math.isfinite(v) and v >= 0 for v in (cpu, seconds, rss)
        ):
            return {"state": "unavailable"}
        return {
            "state": state,
            "cpu_percent": cpu,
            "cpu_seconds": round(seconds, 3),
            "rss_kib": rss,
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"state": "unavailable"}


def observe(
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    expected: bytes,
    *,
    deadline: float = 30,
    limit: float = 120,
) -> dict[str, object]:
    """Observe one process, keeping the original deadline as a failed contract."""
    if not 0 < deadline <= limit <= 120:
        raise ValueError("invalid diagnostic bounds")
    start = time.monotonic()
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    samples: list[dict[str, object]] = []
    crossed = False
    output_exceeded = False
    completion_ms: int | None = None
    parent_exit_ms: int | None = None
    eof: set[str] = set()
    # Sampling is fixed and finite; this is ordinary process telemetry only.
    schedule = sorted(
        {
            0.0,
            deadline / 6,
            deadline / 2,
            deadline,
            min(limit, deadline * 2),
            min(limit, deadline * 3),
            limit,
        }
    )
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    try:
        with selectors.DefaultSelector() as selector:
            for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while True:
                elapsed = time.monotonic() - start
                running = process.poll() is None
                if not running and parent_exit_ms is None:
                    parent_exit_ms = round(elapsed * 1000)
                if not running and not selector.get_map() and completion_ms is None:
                    completion_ms = math.ceil(elapsed * 1000)
                if elapsed >= deadline and (running or selector.get_map()):
                    crossed = True
                if schedule and elapsed >= schedule[0]:
                    schedule.pop(0)
                    sample = (
                        process_state(process.pid) if running else {"state": "exited"}
                    )
                    samples.append(
                        {
                            "elapsed_ms": round(elapsed * 1000),
                            **sample,
                            "load_1m": round(os.getloadavg()[0], 2),
                        }
                    )
                if elapsed >= limit or output_exceeded:
                    break
                if not running and not selector.get_map():
                    break
                for key, _ in selector.select(min(0.05, max(0, limit - elapsed))):
                    data = os.read(key.fd, OUTPUT_LIMIT + 1)
                    if not data:
                        eof.add(cast(str, key.data))
                        selector.unregister(key.fileobj)
                        continue
                    name = cast(str, key.data)
                    remaining = OUTPUT_LIMIT - sum(len(v) for v in chunks.values())
                    chunks[name].extend(data[: max(0, remaining)])
                    if len(data) > remaining:
                        output_exceeded = True
                        break
    finally:
        # Kill the owned group even if a child inherited a pipe after parent exit.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
    elapsed_ms = round((time.monotonic() - start) * 1000)
    version_matches = bytes(chunks["stdout"]).strip() == expected
    return {
        "schema": 1,
        "elapsed_ms": elapsed_ms,
        "deadline_ms": round(deadline * 1000),
        "observation_limit_ms": round(limit * 1000),
        "original_deadline_exceeded": crossed,
        "completion_observed_ms": completion_ms,
        "parent_exit_observed_ms": parent_exit_ms,
        "stdout_eof": "stdout" in eof,
        "stderr_eof": "stderr" in eof,
        "exit_code": process.returncode,
        "stdout_bytes": len(chunks["stdout"]),
        "stderr_bytes": len(chunks["stderr"]),
        "output_limit_exceeded": output_exceeded,
        "version_matches": version_matches,
        "cleanup_completed": process.poll() is not None,
        "contract_passed": completion_ms is not None
        and completion_ms <= round(deadline * 1000)
        and not crossed
        and not output_exceeded
        and process.returncode == 0
        and version_matches,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    harness = os.environ.get("GITHUB_SHA", "")
    if (
        platform_id() != "macos-x86_64"
        or re.fullmatch(r"[0-9a-f]{40}", harness) is None
    ):
        raise SystemExit("diagnostic host/source refused")
    release, bootstrap = admitted(Path("dist/standalone"), SOURCE, VERSION)
    records: list[dict[str, object]] = []
    outcome = "diagnostic_smoke_failed"

    class DiagnosticComplete(Exception):
        pass

    def verify(directory: Path, version: str) -> None:
        if len(records) >= 4:
            raise ReleaseError("diagnostic observation budget exhausted")
        environment = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("OPENAI_", "ANTHROPIC_", "PYTHON", "MOS_"))
        }
        record = observe(
            [str(directory / "mos"), "--version"],
            directory,
            environment,
            f"mos-eisley {version}".encode(),
        )
        record["ordinal"] = len(records) + 1
        record["location"] = (
            "stage" if directory.name.startswith(".stage-") else "existing"
        )
        record["version_kind"] = (
            "synthetic_previous" if version == "0.0.0" else "candidate"
        )
        records.append(record)
        if not record["contract_passed"]:
            raise ReleaseError("diagnostic retained failed staged-version contract")
        if len(records) == 2:
            if record["location"] != "stage" or record["version_kind"] != "candidate":
                raise ReleaseError("unexpected diagnostic fixture phase")
            # Stop at the exact original failing call, before target activation.
            raise DiagnosticComplete

    try:
        # Original assertions and 30-second contract remain; only observation differs.
        with (
            patch.object(app_install, "verify_binary", verify),
            patch(
                "sys.argv",
                [
                    "smoke_app_distribution",
                    "--published-metadata",
                    "dist/standalone/release.json",
                ],
            ),
        ):
            result = smoke_app_distribution.main()
            outcome = "diagnostic_smoke_completed" if result == 0 else outcome
    except DiagnosticComplete:
        outcome = "diagnostic_target_completed_within_original_deadline"
    except (Exception, SystemExit):
        # Raw exception/output is deliberately excluded from this receipt.
        pass
    finally:
        receipt = {
            "schema": 1,
            "status": outcome,
            "provider_calls": 0,
            "qualification_pass": False,
            "records": records,
            "observation_count": len(records),
            "original_failure_preserved": True,
            "source_commit": SOURCE,
            "harness_source": harness,
            "platform": platform_id(),
            "version": release.version,
            "metadata_sha256": hashlib.sha256(
                Path("dist/standalone/release.json").read_bytes()
            ).hexdigest(),
            "archive_sha256": release.artifact(platform_id()).sha256,
            "bootstrap_sha256": hashlib.sha256(bootstrap.read_bytes()).hexdigest(),
        }
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        print(json.dumps({"status": outcome, "observations": len(records)}))
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
