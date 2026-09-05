"""Exercise the actual Docker boundary, including denial and cleanup probes."""

import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mos_eisley.core.models import Brief, Critique
from mos_eisley.evaluation.execution import (
    EvaluationCassette,
    EvaluationRequest,
    ExecutionBatch,
    RecordedExchange,
)
from mos_eisley.evaluation.models import RouteCandidate
from mos_eisley.run.isolation import (
    OfflineContainer,
    bounded_process,
    run_isolated_recorded,
)

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
    container = OfflineContainer(Path(docker), image)
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
    for code in ("import time; time.sleep(10)", "print('x'*17000000)"):
        try:
            container.execute(("-c", code), b"", timeout=2)
        except ValueError as error:
            expected = "deadline" if "sleep" in code else "output exceeds"
            assert expected in str(error), str(error)
        else:
            raise AssertionError("resource violation was accepted")
    after = bounded_process([docker, "ps", "-aq", "--filter", "name=mos-eval-"])
    assert set(after.split()) <= set(before.split()), "isolated containers leaked"
    print("isolated fixture, containment, output/deadline and cleanup checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
