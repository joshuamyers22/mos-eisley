"""Offline synthetic resource probes; no accepted task source is executed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.store import private_write

PIDS = """
import errno, subprocess, sys
from pathlib import Path
assert Path('/sys/fs/cgroup/pids.max').read_text().strip() == '32'
assert Path('/sys/fs/cgroup/memory.max').read_text().strip() == '536870912'
assert Path('/sys/fs/cgroup/cpu.max').read_text().strip() == '100000 100000'
children = []
denied = False
try:
    for _ in range(40):
        try:
            children.append(subprocess.Popen([sys.executable, '-c',
                                             'import time; time.sleep(20)']))
        except OSError as error:
            assert error.errno == errno.EAGAIN
            denied = True
            break
    assert denied, 'process limit did not deny bounded spawn attempts'
finally:
    for child in children:
        child.terminate()
    for child in children:
        child.wait(timeout=5)
print('pids-denied')
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    probes = (
        ("pids-limit", PIDS, None),
        ("output-limit", "print('x' * 17000000)", "output exceeds"),
        ("deadline", "import time; time.sleep(20)", "deadline"),
        ("memory-limit", "bytearray(600 * 1024 * 1024)", "process failed"),
    )
    results = []
    with TemporaryDirectory(prefix="g4-negative-containment-") as directory:
        root = Path(directory)
        for name, code, expected in probes:
            container = OfflineContainer(args.docker, args.image, root / name)
            try:
                output = container.execute(("-c", code), b"", timeout=10)
            except ValueError as error:
                if expected is None or expected not in str(error):
                    raise
            else:
                if expected is not None or output != b"pids-denied\n":
                    raise ValueError(f"probe {name} did not meet its denial contract")
            if container.lifecycle_path is None:
                raise ValueError("probe omitted cleanup evidence")
            cleanup = container.lifecycle_path / "result.json"
            raw = cleanup.read_bytes()
            if json.loads(raw)["state"] != "removed":
                raise ValueError("probe container cleanup was not confirmed")
            results.append(
                {
                    "probe": name,
                    "scenario_sha256": hashlib.sha256(code.encode()).hexdigest(),
                    "expected": expected or "pids-denied",
                    "passed": True,
                    "cleanup_sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        # Retain concise evidence before the temporary lifecycle tree disappears.
        receipt = {
            "kind": "g4_synthetic_negative_containment_receipt",
            "schema_version": 1,
            "image": args.image,
            "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "controller_sha256": hashlib.sha256(
                Path(__file__)
                .parents[1]
                .joinpath("src/mos_eisley/run/isolation.py")
                .read_bytes()
            ).hexdigest(),
            "accepted_task_execution": False,
            "provider_requests": 0,
            "results": results,
            "cleanup_records": [
                json.loads(path.read_bytes())
                for path in sorted(root.rglob("result.json"))
            ],
        }
        private_write(
            args.output,
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode(),
        )
    print(f"Verified {len(results)} offline probes; receipt: {args.output}")


if __name__ == "__main__":
    main()
