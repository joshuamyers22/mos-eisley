"""Exercise only the bounded-reader contract from an installed wheel."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-native-windows", action="store_true")
    args = parser.parse_args()
    if args.require_native_windows and sys.platform != "win32":
        parser.error("native Windows execution is required")
    repository = Path(__file__).resolve().parents[1]
    wheel = repository / "dist/mos_eisley-0.1.0-py3-none-any.whl"
    with TemporaryDirectory(prefix="mos-platform-wheel-") as directory:
        root = Path(directory)
        venv = root / "venv"
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(["uv", "venv", str(venv), "--python", "3.12"], check=True)
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
            check=True,
        )
        # These isolated modules depend only on the standard library. Avoid CLI
        # import and avoid qualifying unrelated runtime/platform contracts.
        shutil.copyfile(
            repository / "tests/test_platform_files.py", root / "test_platform_files.py"
        )
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import pathlib, sys; "
                "import mos_eisley.platform.files as files; "
                "location = pathlib.Path(files.__file__); "
                "assert location.is_relative_to(pathlib.Path(sys.prefix)); "
                "assert 'mos_eisley.platform.posix_files' not in sys.modules",
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        selection = (
            ["test_platform_files.PlatformFileContractTests"]
            if args.require_native_windows
            else ["discover", "-s", str(root), "-p", "test_platform_files.py"]
        )
        subprocess.run(
            [str(python), "-m", "unittest", *selection, "-v"],
            cwd=root,
            env=environment,
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
