"""Creator-test controls, worker resource bounds and exact handoff receipts."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_coding_controller import IMAGE, cassette_for
from test_coding_vcs import good_patch, make_brief

from mos_eisley.coding_child import CodeFile, CodeSnapshot
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.coding_child import (
    CodingAck,
    CodingContainer,
    CodingJob,
    DockerCodingChild,
)
from mos_eisley.run.coding_child_worker import execute_wire, verify_snapshot
from mos_eisley.run.duplex import ExchangeHandler


class FixtureContainer(CodingContainer):
    def __init__(self, root: Path):
        super().__init__(Path("/usr/bin/docker"), IMAGE, root)
        self.forged = False

    async def exchange_async(
        self,
        arguments: tuple[str, ...],
        payload: bytes,
        exchange_handler: ExchangeHandler,
        timeout: float = 30,
    ) -> bytes:
        wire = await exchange_handler(payload)
        output = await execute_wire(arguments[-1], wire, isolate_tests=False)
        if self.forged:
            acknowledgement = CodingAck.model_validate_json(output)
            output = canonical_bytes(
                acknowledgement.model_copy(update={"execution_sha256": "0" * 64})
            )
        return output


class CodingWorkerTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        files = CodeSnapshot(
            files=(
                CodeFile(path="adder.py", content="def add(a,b):\n    return 0\n"),
                CodeFile(
                    path="tests/test_adder.py",
                    content=(
                        "import unittest\nfrom adder import add\n"
                        "class Tests(unittest.TestCase):\n"
                        "    def test_add(self):\n"
                        "        self.assertEqual(add(2,3),5)\n"
                    ),
                ),
            )
        )
        self.brief = make_brief(self.root, self.root / "child", "a" * 40, files)

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_known_bad_baseline_fails_and_correct_patch_passes(self) -> None:
        baseline = await verify_snapshot(self.brief, self.brief.snapshot)
        self.assertFalse(baseline.passed)
        patch = good_patch(self.brief)
        result = await verify_snapshot(self.brief, patch.apply(self.brief))
        self.assertTrue(result.passed)
        self.assertEqual(result.tests_sha256, self.brief.assignment.tests_sha256)
        self.assertEqual(result.snapshot_sha256, patch.apply(self.brief).sha256)

    async def test_snapshot_mutation_or_extra_files_fails_verification(self) -> None:
        patch = good_patch(self.brief)
        snapshot = patch.apply(self.brief)
        old = snapshot.files[0]
        for prefix in (
            'open("extra.py","w").write("injected")\n',
            'open("tests/test_adder.py","w").write("weakened")\n',
        ):
            source = old.model_copy(update={"content": prefix + old.content})
            changed = snapshot.model_copy(update={"files": (source, snapshot.files[1])})
            receipt = await verify_snapshot(self.brief, changed)
            self.assertFalse(receipt.passed)

    async def test_test_output_and_wall_time_are_bounded(self) -> None:
        brief = self.brief.model_copy(update={"wall_seconds": 1})
        snapshot = good_patch(self.brief).apply(self.brief)
        for prefix in ('print("x"*40000)\n', "import time\ntime.sleep(10)\n"):
            tests = snapshot.files[1].model_copy(
                update={"content": prefix + snapshot.files[1].content}
            )
            changed = snapshot.model_copy(update={"files": (snapshot.files[0], tests)})
            with self.assertRaises((ValueError, TimeoutError)):
                await verify_snapshot(brief, changed)

    async def test_no_skipped_or_empty_test_success(self) -> None:
        snapshot = good_patch(self.brief).apply(self.brief)
        for code in (
            "import unittest\n",
            (
                "import unittest\nclass Tests(unittest.TestCase):\n"
                '    @unittest.skip("skip")\n    def test_skip(self): pass\n'
            ),
        ):
            changed = snapshot.model_copy(
                update={
                    "files": (
                        snapshot.files[0],
                        snapshot.files[1].model_copy(update={"content": code}),
                    )
                }
            )
            result = await verify_snapshot(self.brief, changed)
            self.assertFalse(result.passed)

    async def test_exact_wire_and_forged_execution_rejection(self) -> None:
        container = FixtureContainer(self.root)
        executor = DockerCodingChild(container)
        patch = good_patch(self.brief)
        job = CodingJob(brief=self.brief, cassette=cassette_for(self.brief, patch))
        actual = await executor.execute(job)
        self.assertEqual(actual.patch, patch)
        self.assertTrue(actual.verification.passed)
        container.forged = True
        with self.assertRaises(ValueError):
            await executor.execute(job)
        self.assertEqual(digest(canonical_bytes(actual.patch)), patch.sha256)

    async def test_verifier_rejects_changed_protected_tests(self) -> None:
        executor = DockerCodingChild(FixtureContainer(self.root))
        snapshot = good_patch(self.brief).apply(self.brief)
        changed = snapshot.model_copy(
            update={
                "files": (
                    snapshot.files[0],
                    snapshot.files[1].model_copy(update={"content": "pass\n"}),
                )
            }
        )
        with self.assertRaises(ValueError):
            await executor.verify(self.brief, changed)

    async def test_early_zero_exit_does_not_count_as_test_completion(self) -> None:
        snapshot = good_patch(self.brief).apply(self.brief)
        source = snapshot.files[0].model_copy(
            update={"content": "import os\nos._exit(0)\n"}
        )
        altered = snapshot.model_copy(update={"files": (source, snapshot.files[1])})
        receipt = await verify_snapshot(self.brief, altered)
        self.assertFalse(receipt.passed)

    async def test_coding_container_separates_supervisor_and_test_authority(
        self,
    ) -> None:
        command = CodingContainer(
            Path("/usr/bin/docker"), IMAGE, self.root
        ).create_command(
            "fixed", ("-m", "mos_eisley.run.coding_child_worker", "implement")
        )
        self.assertEqual(command[command.index("--user") + 1], "0:0")
        self.assertIn("--read-only", command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command[command.index("--cap-drop") + 1], "ALL")
        self.assertEqual(
            [command[i + 1] for i, x in enumerate(command) if x == "--cap-add"],
            ["SETUID", "SETGID", "KILL"],
        )
        self.assertNotIn("--volume", command)
        self.assertNotIn("--mount", command)

    async def test_source_cannot_introspect_or_weaken_the_test_runtime(self) -> None:
        snapshot = good_patch(self.brief).apply(self.brief)
        for content in (
            "import unittest\nunittest.TestCase.assertEqual = lambda *a: None\n",
            "def add(a,b):\n    return eval('a+b')\n",
            (
                "def helper():\n    return 0\ndef add(a,b):\n"
                "    helper = eval\n    return helper('a+b')\n"
            ),
            "def add(a,b):\n    return (0).__class__\n",
            "def add(a,b):\n    global runtime\n    return 0\n",
            "def add(a,b=print('tamper')):\n    return 0\n",
        ):
            source = snapshot.files[0].model_copy(update={"content": content})
            changed = snapshot.model_copy(update={"files": (source, snapshot.files[1])})
            self.assertFalse((await verify_snapshot(self.brief, changed)).passed)

    async def test_each_selected_nested_file_runs_and_empty_files_fail(self) -> None:
        snapshot = good_patch(self.brief).apply(self.brief)
        for nested in (
            (
                "import unittest\nclass Tests(unittest.TestCase):\n"
                "    def test_fails(self): self.fail('Must execute selected file')\n"
            ),
            "import unittest\n",
            (
                "import unittest\nclass Tests(unittest.TestCase):\n"
                "    def test_passes(self): self.assertTrue(True)\n"
            ),
        ):
            files = CodeSnapshot(
                files=(
                    *snapshot.files,
                    CodeFile(path="tests/test_nested/test_bad.py", content=nested),
                )
            )
            brief = self.brief.model_copy(
                update={
                    "snapshot": files,
                    "test_paths": (
                        "tests/test_adder.py",
                        "tests/test_nested/test_bad.py",
                    ),
                }
            )
            brief = brief.model_copy(
                update={
                    "assignment": brief.assignment.model_copy(
                        update={"tests_sha256": brief.tests_sha256}
                    )
                }
            )
            result = await verify_snapshot(brief, files)
            self.assertEqual(result.passed, "test_passes" in nested)
