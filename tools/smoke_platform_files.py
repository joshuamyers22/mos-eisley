"""Exercise isolated file/identity contracts from an installed wheel."""

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
        for name in (
            "test_platform_files.py",
            "test_platform_identity.py",
            "test_platform_identity_wire.py",
            "test_identity_legacy_fixtures.py",
            "test_platform_windows_principal.py",
            "test_platform_windows_file_identity.py",
        ):
            shutil.copyfile(repository / "tests" / name, root / name)
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        import_check = """
import ctypes
import pathlib
import sys
from unittest.mock import patch
import mos_eisley.platform.files as files
import mos_eisley.platform.identity as identity
import mos_eisley.platform.identity_wire as wire
assert 'mos_eisley.platform.posix_files' not in sys.modules
assert 'mos_eisley.platform.posix_identity' not in sys.modules
assert 'mos_eisley.platform.windows_identity' not in sys.modules
assert 'mos_eisley.platform.windows_file_identity' not in sys.modules
with patch.object(ctypes, 'WinDLL', create=True,
                  side_effect=AssertionError('eager system DLL loading')):
    import mos_eisley.platform.windows_identity as candidate
    import mos_eisley.platform.windows_file_identity as file_candidate
for module in (files, identity, wire, candidate, file_candidate):
    assert pathlib.Path(module.__file__).is_relative_to(pathlib.Path(sys.prefix))
"""
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                import_check,
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        selection = (
            [
                "test_platform_files.PlatformFileContractTests",
                "test_platform_identity.IdentityValueTests",
                "test_platform_identity_wire.IdentityWireTests",
                "test_platform_identity.IdentityContractTests",
                "test_platform_windows_principal.WindowsPrincipalFaultTests",
                "test_platform_windows_principal.NativeTokenBindingTests",
                "test_platform_windows_principal.NativeWindowsPrincipalTests",
                "test_platform_windows_file_identity.WindowsFileFaultTests",
                "test_platform_windows_file_identity.NativeFileBindingTests",
                "test_platform_windows_file_identity.NativeWindowsFileIdentityTests",
            ]
            if args.require_native_windows
            else ["discover", "-s", str(root), "-p", "test_platform_*.py"]
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "unittest",
                "test_identity_legacy_fixtures.LegacyFixtureBytesTests",
                "-v",
            ],
            cwd=root,
            env=environment,
            check=True,
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
