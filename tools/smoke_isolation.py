"""Exercise the actual Docker boundary, including denial and cleanup probes."""

import asyncio
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import JsonValue

from mos_eisley.core.models import Brief, Critique, canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.skills import PromptAsset
from mos_eisley.evaluation.execution import (
    EvaluationCassette,
    EvaluationRequest,
    ExecutionBatch,
    RecordedExchange,
)
from mos_eisley.evaluation.models import RouteCandidate
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport, SpendPolicy
from mos_eisley.run.isolated_broker import run_isolated_broker
from mos_eisley.run.isolation import (
    OfflineContainer,
    bounded_process,
    run_isolated_recorded,
)
from mos_eisley.run.provider_broker import RequestBoundBroker
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.watchdog import CleanupLease, CleanupRecord, remove_exact

PROBE = """
import errno, os, socket, sys
from pathlib import Path
assert os.getuid() == 10001
assert 'OPENAI_API_KEY' not in os.environ
host_file = Path(sys.stdin.read().strip())
assert not host_file.exists(), 'host canary is readable'
assert not Path('/var/run/docker.sock').exists()
assert not Path('/run/docker.sock').exists()
try:
    Path('/app/.venv/forbidden-write').write_text('denied')
except OSError as error:
    assert error.errno == errno.EROFS
else:
    raise AssertionError('image filesystem is writable')
status = Path('/proc/self/status').read_text()
assert 'NoNewPrivs:\\t1' in status
assert 'CapEff:\\t0000000000000000' in status
assert 'Seccomp:\\t2' in status
for _, name in socket.if_nameindex():
    if name != 'lo':
        flags = int(Path('/sys/class/net', name, 'flags').read_text(), 16)
        assert not flags & 1, 'non-loopback interface is up'
assert Path('/sys/fs/cgroup/pids.max').read_text().strip() == '32'
assert Path('/sys/fs/cgroup/memory.max').read_text().strip() == '536870912'
assert Path('/sys/fs/cgroup/cpu.max').read_text().strip() == '100000 100000'
with socket.socket() as connection:
    connection.settimeout(0.5)
    try:
        connection.connect(('192.0.2.1', 9))
    except OSError:
        pass
    else:
        raise AssertionError('unexpected network reachability')
Path('/tmp/allowed-write').write_text('ephemeral')
print('containment probes passed')
"""


def check_broker(container: OfflineContainer, root: Path) -> None:
    """Real offline container, real spending ledger, synthetic host transport."""

    class FixtureTransport:
        calls = 0

        async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
            return 10

        async def create_response(
            self, payload: dict[str, JsonValue]
        ) -> dict[str, JsonValue]:
            self.calls += 1
            assert ledger.snapshot().charged_microusd == 30
            return {
                "model": "fixture-model",
                "service_tier": "default",
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "output": "synthetic host response",
            }

    root.mkdir(mode=0o700)
    ledger = SpendLedger.create(root / "ledger.sqlite", 100)
    fixture = FixtureTransport()
    now = datetime.now(UTC)
    policy = SpendPolicy(
        model="fixture-model",
        pricing_source="synthetic IPC test rates",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=5),
        input_microusd_per_million=1_000_000,
        output_microusd_per_million=2_000_000,
        max_cost_microusd=100,
    )
    payload: dict[str, JsonValue] = {
        "model": "fixture-model",
        "input": [{"role": "user", "content": "Fixture"}],
        "max_output_tokens": 10,
        "tools": [],
    }
    broker = RequestBoundBroker(
        payload,
        BudgetedOpenAITransport(fixture, policy, root, ledger),
        lifetime_seconds=60,
    )

    async def handle(wire: bytes) -> bytes:
        await broker.redeem(wire)
        raise AssertionError("tampered claim reached provider")

    tamper = """
import json, sys
claim = json.loads(sys.stdin.readline())
claim['request_sha256'] = '0' * 64
print(json.dumps(claim), flush=True)
sys.stdin.readline()
"""
    try:
        container.execute(
            ("-c", tamper), canonical_bytes(broker.claim()), exchange_handler=handle
        )
    except ProviderError:
        pass
    else:
        raise AssertionError("tampered worker grant accepted")
    assert fixture.calls == 0 and ledger.snapshot().charged_microusd == 0
    reply = run_isolated_broker(broker, container)
    assert reply.response["output"] == "synthetic host response"
    assert fixture.calls == 1 and ledger.snapshot().charged_microusd == 20
    try:
        run_isolated_broker(broker, container)
    except ProviderError:
        pass
    else:
        raise AssertionError("worker replay accepted")
    assert fixture.calls == 1

    cancelled: list[bool] = []

    async def pending(wire: bytes) -> bytes:
        try:
            await asyncio.sleep(10)
            return b"unreachable"
        finally:
            cancelled.append(True)

    disconnect = """
import sys, time
print(sys.stdin.readline().strip(), flush=True)
time.sleep(1)
"""
    try:
        container.execute(
            ("-c", disconnect), b"fixture-grant", exchange_handler=pending
        )
    except ValueError:
        pass
    else:
        raise AssertionError("disconnected worker exchange accepted")
    assert cancelled == [True], "disconnect did not cancel host work"
    try:
        container.execute(
            ("-c", "print('x'*5000)"), b"fixture-grant", exchange_handler=pending
        )
    except ValueError:
        pass
    else:
        raise AssertionError("oversized worker frame accepted")
    assert cancelled == [True], "oversized frame dispatched host work"


def check_launcher_death(docker: str, image: str, root: Path) -> None:
    script = """
import sys
from pathlib import Path
from mos_eisley.run.isolation import OfflineContainer
OfflineContainer(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])).execute(
    ('-c', 'import time; time.sleep(60)'), b'', timeout=60)
"""
    container_id: str | None = None
    with subprocess.Popen(
        [sys.executable, "-c", script, docker, image, str(root)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    ) as launcher:
        try:
            deadline = time.monotonic() + 15
            receipt_path: Path | None = None
            while time.monotonic() < deadline:
                leases = list(root.glob("*/armed.json"))
                if leases:
                    directory = leases[0].parent
                    lease = CleanupLease.model_validate_json(
                        (directory / "lease.json").read_bytes()
                    )
                    container_id = lease.container_id
                    running = bounded_process(
                        [
                            docker,
                            "inspect",
                            "--format",
                            "{{.State.Running}}",
                            container_id,
                        ],
                        timeout=2,
                    ).strip()
                    if running == b"true":
                        receipt_path = directory / "result.json"
                        break
                if launcher.poll() is not None:
                    raise AssertionError("launcher exited before crash probe was armed")
                time.sleep(0.05)
            assert receipt_path is not None, "watchdog did not arm a running worker"
            launcher.kill()  # SIGKILL: no Python finally/atexit cleanup can run.
            launcher.wait(timeout=5)
            deadline = time.monotonic() + 15
            result: CleanupRecord | None = None
            while time.monotonic() < deadline:
                try:
                    result = CleanupRecord.model_validate_json(
                        receipt_path.read_bytes()
                    )
                except (ValueError, OSError):
                    time.sleep(0.05)
                else:
                    break
            assert result is not None, "watchdog did not write a valid cleanup receipt"
            assert result.state == "removed" and result.container_id == container_id
            remaining = bounded_process(
                [
                    docker,
                    "ps",
                    "--all",
                    "--no-trunc",
                    "--format",
                    "{{.ID}}",
                    "--filter",
                    "id=" + result.container_id,
                ]
            )
            assert not remaining.strip(), "watchdog reported removal but worker remains"
        finally:
            if launcher.poll() is None:
                launcher.kill()
                launcher.wait(timeout=5)
            if container_id is not None:
                remove_exact(docker, container_id)


def main() -> int:
    docker = shutil.which("docker")
    if docker is None:
        raise ValueError("Docker executable required")
    image = (
        bounded_process(
            [docker, "image", "inspect", "--format", "{{.Id}}", "mos-eisley:local"]
        )
        .decode()
        .strip()
    )
    with TemporaryDirectory(prefix="mos-lifecycle-smoke-") as directory:
        return check_boundary(docker, image, Path(directory))


def check_boundary(docker: str, image: str, root: Path) -> int:
    container = OfflineContainer(Path(docker), image, root / "normal")
    before = bounded_process([docker, "ps", "-aq", "--filter", "name=mos-eval-"])
    with TemporaryDirectory(prefix="mos-host-label-") as directory:
        canary = Path(directory) / "private-label.txt"
        canary.write_text("host-only expected finding")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-canary-not-a-credential"}):
            output = container.execute(("-c", PROBE), str(canary).encode())
        assert output == b"containment probes passed\n"
    request = EvaluationRequest(
        sample_id="a" * 64,
        route=RouteCandidate(
            backend="fixture",
            provider="fixture",
            model="reviewer-v1",
            effort="low",
            client_version="fixture/1",
            registry_sha256="b" * 64,
            prompt=PromptAsset(
                mode="inline", instructions="Run the containment smoke review."
            ),
        ),
        brief=Brief(spec="Return one.", diff="return 1"),
    )
    batch = ExecutionBatch(plan_sha256="c" * 64, requests=(request,))
    cassette = EvaluationCassette(
        batch_sha256=batch.batch_sha256,
        exchanges=(
            RecordedExchange(
                request_sha256=request.request_sha256,
                response=Critique(findings=()),
                latency_ms=0,
                cost_microusd=0,
            ),
        ),
    )
    result = run_isolated_recorded(batch, cassette, container)
    assert len(result.results) == 1
    assert container.lifecycle_path is not None
    receipt = CleanupRecord.model_validate_json(
        (container.lifecycle_path / "result.json").read_bytes()
    )
    assert receipt.state == "removed"
    for code in ("import time; time.sleep(10)", "print('x'*17000000)"):
        try:
            container.execute(("-c", code), b"", timeout=2)
        except ValueError as error:
            expected = "deadline" if "sleep" in code else "output exceeds"
            assert expected in str(error), str(error)
        else:
            raise AssertionError("resource violation was accepted")
    check_launcher_death(docker, image, root / "killed-launcher")
    check_broker(container, root / "broker-spending")
    after = bounded_process([docker, "ps", "-aq", "--filter", "name=mos-eval-"])
    assert set(after.split()) <= set(before.split()), "isolated containers leaked"
    print("containment, fixtures, broker IPC, limits and crash cleanup passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
