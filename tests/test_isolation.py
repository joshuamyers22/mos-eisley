"""Bounded pipes, immutable images, fixed confinement flags and cleanup ordering."""

import json
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from pydantic import JsonValue
from test_evaluation_execution import complete_cassette, inputs

from mos_eisley.core.models import canonical_bytes
from mos_eisley.evaluation.execution import (
    make_execution_batch,
    run_recorded_evaluation,
)
from mos_eisley.evaluation.scoring import make_plan
from mos_eisley.run.isolation import (
    MAX_WIRE_BYTES,
    OfflineContainer,
    RecordedJob,
    bounded_process,
    run_isolated_recorded,
)

IMAGE = "sha256:" + "a" * 64


class IsolationTests(TestCase):
    def test_pipe_limits_deadlines_failure_and_environment(self) -> None:
        python = sys.executable
        self.assertEqual(bounded_process([python, "-c", "print('ok')"]), b"ok\n")
        for script in (
            "print('x'*10000)",
            "import sys; sys.stderr.write('secret'*20000)",
            "import time; time.sleep(10)",
            "import sys; sys.exit(2)",
        ):
            with self.subTest(script=script), self.assertRaises(ValueError):
                bounded_process([python, "-c", script], timeout=0.2, limit=100)
        with self.assertRaises(ValueError):
            bounded_process([python], b"x" * (MAX_WIRE_BYTES + 1))
        with patch.dict("os.environ", {"OPENAI_API_KEY": "private-test-canary"}):
            self.assertEqual(
                bounded_process(
                    [python, "-c", "import os; print('OPENAI_API_KEY' in os.environ)"]
                ),
                b"False\n",
            )

    def test_fixed_container_flags_and_cleanup(self) -> None:
        metadata = json.dumps([{"Id": IMAGE, "Config": {}}]).encode()
        with patch(
            "mos_eisley.run.isolation.bounded_process",
            side_effect=[metadata, b"container-id", b"output", b"0\n", b"removed"],
        ) as command:
            output = OfflineContainer(Path("/usr/bin/docker"), IMAGE).execute(
                ("-c", "pass"), b"input"
            )
        self.assertEqual(output, b"output")
        create = command.call_args_list[1].args[0]
        for option in (
            "--read-only",
            "--cap-drop",
            "--pids-limit",
            "--memory",
            "--cpus",
        ):
            self.assertIn(option, create)
        for option in ("--volume", "--mount", "--privileged", "--env"):
            self.assertNotIn(option, create)
        self.assertEqual(create[create.index("--network") + 1], "none")
        self.assertEqual(create[create.index("--user") + 1], "10001:10001")
        self.assertEqual(command.call_args_list[-1].args[0][1:3], ["rm", "--force"])

    def test_failure_still_removes_and_cleanup_failure_is_not_success(self) -> None:
        metadata = json.dumps([{"Id": IMAGE, "Config": {}}]).encode()
        cases = (
            [metadata, ValueError("create failed"), b"removed"],
            [metadata, b"id", ValueError("deadline"), b"removed"],
            [metadata, b"id", b"output", b"1", b"removed"],
            [metadata, b"id", b"output", b"0", ValueError("cleanup failed")],
        )
        for results in cases:
            with (
                self.subTest(results=results),
                patch(
                    "mos_eisley.run.isolation.bounded_process",
                    side_effect=results,
                ) as command,
                self.assertRaises(ValueError),
            ):
                OfflineContainer(Path("/usr/bin/docker"), IMAGE).execute(
                    ("-c", "pass"), b""
                )
            self.assertEqual(command.call_args_list[-1].args[0][1:3], ["rm", "--force"])

    def test_tags_volumes_and_bad_bounds_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OfflineContainer(Path("/usr/bin/docker"), "project:latest")
        with self.assertRaises(ValueError):
            OfflineContainer(Path("docker"), IMAGE)
        container = OfflineContainer(Path("/usr/bin/docker"), IMAGE)
        with self.assertRaises(ValueError):
            container.execute((), b"", timeout=61)
        cases: tuple[JsonValue, ...] = (
            [],
            [{"Id": IMAGE, "Config": {"Volumes": {"/data": {}}}}],
            [None],
        )
        for metadata in cases:
            with (
                patch(
                    "mos_eisley.run.isolation.bounded_process",
                    return_value=json.dumps(metadata).encode(),
                ) as command,
                self.assertRaises(ValueError),
            ):
                container.execute((), b"")
            self.assertEqual(command.call_count, 1)

    def test_recorded_worker_roundtrip_and_changed_output_rejected(self) -> None:
        data, grid, gate = inputs()
        plan = make_plan(data, grid, 1, 0, gate)
        batch, _ = make_execution_batch(plan, data, "calibration", b"a" * 32)
        cassette = complete_cassette(
            batch.batch_sha256, tuple(r.request_sha256 for r in batch.requests)
        )
        payload = canonical_bytes(RecordedJob(batch=batch, cassette=cassette))
        output = bounded_process(
            [sys.executable, "-m", "mos_eisley.run.evaluation_worker"], payload
        )
        expected = run_recorded_evaluation(batch, cassette)
        self.assertEqual(output, canonical_bytes(expected))
        container = OfflineContainer(Path("/usr/bin/docker"), IMAGE)
        with patch.object(container, "execute", return_value=output):
            self.assertEqual(
                run_isolated_recorded(batch, cassette, container), expected
            )
        changed = expected.model_copy(update={"batch_sha256": "b" * 64})
        with (
            patch.object(container, "execute", return_value=canonical_bytes(changed)),
            self.assertRaises(ValueError),
        ):
            run_isolated_recorded(batch, cassette, container)
        with self.assertRaises(ValueError):
            bounded_process(
                [sys.executable, "-m", "mos_eisley.run.evaluation_worker"],
                b"invalid secret",
            )
