"""Fixed frozen dispatch preserves confinement and ordinary CLI routing."""

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from mos_eisley import _frozen_entry, _git_read_linux
from mos_eisley.conversation_git_isolation import isolated_command
from mos_eisley.run import watchdog


class FrozenEntryTests(TestCase):
    def test_watchdog_requires_frozen_posix_and_dispatches_exact_arguments(
        self,
    ) -> None:
        arguments = ["--docker", "/usr/bin/true", "--lease-fd", "7"]
        for system, frozen, admitted in (
            ("darwin", True, True),
            ("linux", True, True),
            ("win32", True, False),
            ("darwin", False, False),
            ("linux", False, False),
        ):
            with (
                self.subTest(system=system, frozen=frozen),
                patch.object(sys, "platform", system),
                patch.object(sys, "frozen", frozen, create=True),
                patch.object(watchdog, "main", return_value=1) as helper,
                patch("mos_eisley.cli.main") as cli,
            ):
                self.assertEqual(
                    _frozen_entry.main([_frozen_entry.CONTAINER_WATCHDOG, *arguments]),
                    1 if admitted else 2,
                )
                if admitted:
                    helper.assert_called_once_with(arguments)
                else:
                    helper.assert_not_called()
                cli.assert_not_called()

    def test_linux_frozen_command_uses_fixed_helper_not_python_module_flags(
        self,
    ) -> None:
        with (
            patch.object(sys, "platform", "linux"),
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", "/private/app/mos"),
        ):
            self.assertEqual(
                isolated_command(Path("/usr/bin/git"), ["--version"]),
                [
                    "/private/app/mos",
                    _frozen_entry.LINUX_GIT_READ,
                    "/usr/bin/git",
                    "--version",
                ],
            )
        with (
            patch.object(sys, "platform", "linux"),
            patch.object(sys, "frozen", False, create=True),
        ):
            self.assertEqual(
                isolated_command(Path("/usr/bin/git"), ["--version"])[1:4],
                ["-I", "-m", "mos_eisley._git_read_linux"],
            )

    def test_private_route_requires_frozen_linux_before_helper_entry(self) -> None:
        for system, frozen in (("darwin", True), ("linux", False), ("win32", True)):
            with (
                self.subTest(system=system, frozen=frozen),
                patch.object(sys, "platform", system),
                patch.object(sys, "frozen", frozen, create=True),
                patch.object(_git_read_linux, "main") as helper,
            ):
                self.assertEqual(
                    _frozen_entry.main([_frozen_entry.LINUX_GIT_READ, "/usr/bin/git"]),
                    2,
                )
                helper.assert_not_called()

    def test_frozen_route_delegates_exact_arguments_to_fixed_module(self) -> None:
        with (
            patch.object(sys, "platform", "linux"),
            patch.object(sys, "frozen", True, create=True),
            patch.object(_git_read_linux, "main", return_value=1) as helper,
        ):
            self.assertEqual(
                _frozen_entry.main(
                    [_frozen_entry.LINUX_GIT_READ, "/usr/bin/git", "--version"]
                ),
                1,
            )
            helper.assert_called_once_with(["/usr/bin/git", "--version"])

    def test_invalid_target_or_confinement_failure_cannot_exec(self) -> None:
        with (
            patch.object(_git_read_linux, "_confine") as confine,
            patch.object(_git_read_linux.os, "execv") as execute,
        ):
            for args in ([], ["relative-git"], ["../git", "--version"]):
                self.assertEqual(_git_read_linux.main(args), 2)
            confine.assert_not_called()
            execute.assert_not_called()
        with (
            patch.object(
                _git_read_linux, "_confine", side_effect=OSError("unavailable")
            ),
            patch.object(_git_read_linux.os, "execv") as execute,
        ):
            self.assertEqual(_git_read_linux.main(["/usr/bin/git", "--version"]), 1)
            execute.assert_not_called()

    def test_confinement_precedes_exact_exec_and_cli_arguments_stay_ordinary(
        self,
    ) -> None:
        observed: list[object] = []

        def execute(executable: Path, arguments: list[str]) -> None:
            observed.append((executable, arguments))

        with (
            patch.object(
                _git_read_linux,
                "_confine",
                side_effect=lambda: observed.append("confined"),
            ),
            patch.object(
                _git_read_linux.os,
                "execv",
                side_effect=execute,
            ),
        ):
            self.assertEqual(_git_read_linux.main(["/usr/bin/git", "--version"]), 1)
        self.assertEqual(
            observed,
            ["confined", (Path("/usr/bin/git"), ["/usr/bin/git", "--version"])],
        )
        with patch("mos_eisley.cli.main", return_value=0) as cli:
            self.assertEqual(_frozen_entry.main(["--version"]), 0)
            cli.assert_called_once_with(["--version"])
