"""Exact native §31.7 source/wheel evidence; no provider or release admission."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from typing import cast

MODULES = (
    "test_git_review",
    "test_git_review_ranges",
    "test_git_review_worktrees",
    "test_conversation_git_review",
    "test_scoped_live_review",
    "test_conversation_live_review",
    "test_conversation_review",
    "test_conversation_recovery",
)


def read_json(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError("evidence_too_large")
    value: object = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("evidence_object_required")
    return cast(dict[str, object], value)


def write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def validate_host(host: dict[str, object], commit: str) -> None:
    if (
        host.get("schema_version") != 1
        or host.get("host_os") != "Windows"
        or host.get("candidate_commit") != commit
        or host.get("distribution") != "Ubuntu-24.04"
        or host.get("distribution_version") != 2
        or not isinstance(host.get("windows_build"), str)
        or not str(host["windows_build"]).isdigit()
        or not isinstance(host.get("wsl_version"), str)
        or not host["wsl_version"]
        or not isinstance(host.get("distribution_listing"), str)
        or not re.search(
            r"(?m)^\s*\*?\s*Ubuntu-24\.04\s+\S+\s+2\s*$",
            str(host["distribution_listing"]),
        )
    ):
        raise ValueError("actual_windows_wsl2_host_evidence_required")


def quality_counts(text: str) -> list[dict[str, int | float]]:
    counts = re.findall(
        r"(?m)^Ran (\d+) tests in ([\d.]+)s\s*\n\s*OK(?: \(skipped=(\d+)\))?", text
    )
    if len(counts) != 2 or any(int(total) < 1000 for total, _, _ in counts):
        raise ValueError("complete_source_and_wheel_gate_results_required")
    return [
        {
            "tests_run": int(total),
            "duration_seconds": float(seconds),
            "skipped": int(skipped or 0),
        }
        for total, seconds, skipped in counts
    ]


def verify_wheel(repository: Path, wheel: Path) -> int:
    sources = {
        str(p.relative_to(repository / "src")): p.read_bytes()
        for p in (repository / "src/mos_eisley").rglob("*.py")
    }
    with zipfile.ZipFile(wheel) as archive:
        names = {
            name
            for name in archive.namelist()
            if name.startswith("mos_eisley/") and name.endswith(".py")
        }
        if names != set(sources) or any(
            archive.read(name) != data for name, data in sources.items()
        ):
            raise ValueError("exact_source_wheel_bytes_required")
    return len(sources)


def command(args: list[str], *, cwd: Path, log: Path, timeout: int = 900) -> None:
    print(json.dumps({"command": args, "status": "running"}), flush=True)
    with log.open("w") as stream:
        try:
            subprocess.run(
                args,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=timeout,
            )
        except subprocess.SubprocessError:
            stream.flush()
            print(log.read_text(errors="replace")[-16000:], file=sys.stderr, flush=True)
            raise


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, timeout=20
    ).strip()


def cases(tests: Path, output: Path, mode: str) -> int:
    # -I removes ambient PYTHONPATH/cwd; only the explicit fixture directory is added.
    sys.path.insert(0, str(tests.resolve(strict=True)))
    import mos_eisley

    package = Path(mos_eisley.__file__).resolve()
    repository = Path(__file__).resolve().parents[1]
    if mode == "installed" and not package.is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("installed_package_outside_checkout_required")
    if mode == "source" and not package.is_relative_to(repository / "src"):
        raise ValueError("exact_source_package_required")
    start = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and not result.skipped and result.testsRun > 0
    write_json(
        output,
        {
            "schema_version": 1,
            "mode": mode,
            "package": str(package),
            "modules": list(MODULES),
            "tests_run": result.testsRun,
            "duration_seconds": round(time.monotonic() - start, 3),
            "skipped": [test.id() for test, _ in result.skipped],
            "failures": [test.id() for test, _ in result.failures],
            "errors": [test.id() for test, _ in result.errors],
            "passed": passed,
        },
    )
    return 0 if passed else 1


def qualify(target: str, commit: str, output: Path, host_path: Path | None) -> int:
    repository = Path(__file__).resolve().parents[1]
    report: dict[str, object] = {
        "schema_version": 1,
        "scope": "31.7_native_git_review",
        "target": target,
        "candidate_commit": commit,
        "status": "failed",
        "execution_authorized": False,
        "release_authorized": False,
        "system": platform.system(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "uid": os.getuid() if hasattr(os, "getuid") else None,
    }
    try:
        if (
            not re.fullmatch(r"[0-9a-f]{40}", commit)
            or git(repository, "rev-parse", "HEAD") != commit
            or git(repository, "status", "--porcelain")
        ):
            raise ValueError("exact_clean_candidate_required")
        if (
            platform.system() != "Linux"
            or os.getuid() == 0
            or Path("/.dockerenv").exists()
            or Path("/run/.containerenv").exists()
        ):
            raise ValueError("non_root_native_linux_required")
        from mos_eisley.wsl2_preflight import (
            check_directory,
            classify_kernel,
            parse_mounts,
            read_metadata,
        )

        wsl = classify_kernel(platform.system(), platform.release())
        if (target == "wsl2" and wsl != "wsl2_candidate") or (
            target == "linux" and wsl != "not_wsl"
        ):
            raise ValueError("exact_native_target_required")
        mounts = parse_mounts(read_metadata(Path("/proc/self/mountinfo")))
        paths = (repository, Path(tempfile.gettempdir()), Path(sys.prefix))
        directories = [
            check_directory("qualification", path, mounts, os.getuid(), private=False)
            for path in paths
        ]
        if any(item.issues for item in directories):
            raise ValueError("native_ext4_paths_required")
        report["filesystems"] = [
            {"path": d.path, "filesystem": d.filesystem, "mount": d.mount}
            for d in directories
        ]
        report["git"] = git(repository, "--version")
        report["uv"] = subprocess.check_output(
            ["uv", "--version"], text=True, timeout=10
        ).strip()
        if target == "wsl2":
            if host_path is None:
                raise ValueError("windows_host_evidence_required")
            host = read_json(host_path)
            validate_host(host, commit)
            report["windows_host"] = host
        with tempfile.TemporaryDirectory(prefix="mos-native-review-") as directory:
            root = Path(directory)
            quality_log = root / "quality.log"
            command(
                ["make", "check", "-j1"], cwd=repository, log=quality_log, timeout=14400
            )
            report["quality"] = quality_counts(quality_log.read_text(errors="replace"))
            wheels = tuple((repository / "dist").glob("*.whl"))
            wheel = max(wheels, key=lambda p: p.stat().st_mtime_ns)
            report["wheel"] = {
                "python_files": verify_wheel(repository, wheel),
                "name": wheel.name,
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            }
            source = root / "source.json"
            command(
                [
                    sys.executable,
                    "-I",
                    str(Path(__file__).resolve()),
                    "cases",
                    "--tests",
                    str(repository / "tests"),
                    "--mode",
                    "source",
                    "--output",
                    str(source),
                ],
                cwd=root,
                log=root / "source.log",
            )
            report["source_review"] = read_json(source)
            venv = root / "installed"
            python = venv / "bin/python"
            command(
                ["uv", "venv", str(venv), "--python", "3.12"],
                cwd=root,
                log=root / "venv.log",
                timeout=120,
            )
            command(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--require-hashes",
                    "-r",
                    str(repository / "requirements.runtime.txt"),
                ],
                cwd=root,
                log=root / "dependencies.log",
                timeout=600,
            )
            command(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--no-deps",
                    str(wheel),
                ],
                cwd=root,
                log=root / "wheel.log",
                timeout=120,
            )
            tests = root / "tests"
            shutil.copytree(
                repository / "tests",
                tests,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            installed = root / "installed.json"
            command(
                [
                    str(python),
                    "-I",
                    str(Path(__file__).resolve()),
                    "cases",
                    "--tests",
                    str(tests),
                    "--mode",
                    "installed",
                    "--output",
                    str(installed),
                ],
                cwd=root,
                log=root / "installed.log",
            )
            source_result, installed_result = read_json(source), read_json(installed)
            if source_result["tests_run"] != installed_result["tests_run"]:
                raise ValueError("source_wheel_review_case_parity_required")
            report["installed_review"] = installed_result
        if git(repository, "status", "--porcelain"):
            raise ValueError("candidate_changed_during_qualification")
        report["status"] = "passed_for_exact_review_scope"
        return_code = 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report["error_type"] = type(exc).__name__
        report["error_code"] = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]+", str(exc))
            else "qualification_command_failed"
        )
        # Process output and exception messages stay outside the artifact.
        return_code = 1
    write_json(output, report)
    print(json.dumps(report, sort_keys=True), flush=True)
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("qualify")
    run.add_argument("--target", choices=("linux", "wsl2"), required=True)
    run.add_argument("--commit", required=True)
    run.add_argument("--host-evidence", type=Path)
    run.add_argument("--output", type=Path, required=True)
    case = sub.add_parser("cases")
    case.add_argument("--tests", type=Path, required=True)
    case.add_argument("--mode", choices=("source", "installed"), required=True)
    case.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "cases":
        return cases(args.tests, args.output, args.mode)
    return qualify(args.target, args.commit, args.output, args.host_evidence)


if __name__ == "__main__":
    raise SystemExit(main())
