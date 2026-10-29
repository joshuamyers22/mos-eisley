"""Fixed internal helper dispatch for the self-contained executable."""

import sys
from collections.abc import Sequence

LINUX_GIT_READ = "--_mos-linux-git-read"
CONTAINER_WATCHDOG = "--_mos-container-watchdog"


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == CONTAINER_WATCHDOG:
        if sys.platform not in {"darwin", "linux"} or not getattr(sys, "frozen", False):
            return 2
        from mos_eisley.run.watchdog import main as watchdog_main

        return watchdog_main(arguments[1:])
    if arguments and arguments[0] == LINUX_GIT_READ:
        if sys.platform != "linux" or not getattr(sys, "frozen", False):
            return 2
        # Import only the fixed helper before confinement, never the CLI/provider
        # composition root or a caller-selected Python module.
        from mos_eisley._git_read_linux import main as git_main

        return git_main(arguments[1:])

    from mos_eisley.cli import main as cli_main

    return cli_main(arguments)
