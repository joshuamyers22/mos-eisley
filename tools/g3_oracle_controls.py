"""Run bounded, offline public-oracle controls for one G3 source candidate.

Operator-only calibration. Results do not become G3 labels, sampling receipts,
production outcomes, or enrollment evidence without separate owner review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path, PurePosixPath

import duckdb
from g3_candidate_task_views import SOURCE_BYTES, SOURCE_SHA256, source_digest

ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / "docs/G3_SWE_REBENCH_CANDIDATE_FRAME.json"
MAX_LOG_BYTES = 8_000_000
TIMEOUT_SECONDS = 360


def expected_row(source: Path, packet: str) -> tuple[dict, dict]:
    if source_digest(source) != (SOURCE_BYTES, SOURCE_SHA256):
        raise ValueError("source byte count or SHA-256 differs from pinned release")
    frame = json.loads(FRAME.read_text())
    candidates = [
        row
        for row in frame["inspected_rows"]
        if row.get("review_status") == "candidate"
        and Path(row["packet_path"]).stem == packet
    ]
    if len(candidates) != 1:
        raise ValueError("packet is not a pinned candidate")
    candidate = candidates[0]
    with duckdb.connect() as connection:
        rows = connection.execute(
            """SELECT image_name, FAIL_TO_PASS, PASS_TO_PASS,
                      install_config.test_cmd
               FROM read_parquet(?) WHERE instance_id = ?""",
            [str(source), candidate["instance_id"]],
        ).fetchall()
    if len(rows) != 1 or rows[0][3] != "go test -v ./...":
        raise ValueError("pinned oracle row or test command differs")
    image, f2p, p2p, _ = rows[0]
    return candidate, {"image": image, "f2p": f2p, "p2p": p2p}


def patch_targets(data: bytes) -> list[str]:
    targets = []
    for line in data.decode().splitlines():
        if not line.startswith("diff --git a/"):
            continue
        names = line[len("diff --git ") :].split(" b/", 1)
        if len(names) != 2 or not names[0].startswith("a/"):
            raise ValueError("unexpected patch file header")
        path = names[1]
        parts = PurePosixPath(path).parts
        if not parts or any(part in {".", "..", ".git"} for part in parts):
            raise ValueError("unsafe patch target")
        targets.append(path)
    if not targets:
        raise ValueError("patch has no file targets")
    return targets


def apply_patch(workspace: Path, patch: Path) -> None:
    data = patch.read_bytes()
    patch_targets(data)
    for args in (["git", "apply", "--check", str(patch)], ["git", "apply", str(patch)]):
        completed = subprocess.run(args, cwd=workspace, capture_output=True, timeout=30)
        if completed.returncode:
            raise ValueError(
                f"patch application failed: {patch.name}: {completed.stderr[:500]!r}"
            )


def score(log: str, exit_code: int, expected: dict, kind: str) -> dict:
    terminal: dict[str, list[tuple[str, str]]] = defaultdict(list)
    malformed = 0
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(event, dict):
            malformed += 1
            continue
        action = event.get("Action")
        name = event.get("Test")
        package = event.get("Package")
        if action in {"pass", "fail", "skip"} and name:
            if not isinstance(package, str) or not isinstance(name, str):
                malformed += 1
            else:
                terminal[name].append((package, action))
    repeated_pair = sorted(
        name for name, values in terminal.items() if len(values) != len(set(values))
    )
    multi_package = sorted(
        name
        for name, values in terminal.items()
        if len({package for package, _ in values}) > 1
    )
    conflicting = sorted(
        name
        for name, values in terminal.items()
        if len({action for _, action in values}) > 1
    )
    desired = "pass" if kind == "gold" else "fail"
    f2p = {
        name: (
            "missing"
            if name not in terminal
            else desired
            if all(action == desired for _, action in terminal[name])
            else "mixed_or_wrong"
        )
        for name in expected["f2p"]
    }
    p2p_ok = sum(
        name in terminal and all(action == "pass" for _, action in terminal[name])
        for name in expected["p2p"]
    )
    unexpected_fail = sorted(
        name
        for name, values in terminal.items()
        if any(action == "fail" for _, action in values) and name not in expected["f2p"]
    )
    accepted = (
        malformed == 0
        and not repeated_pair
        and not conflicting
        and exit_code == (0 if kind == "gold" else 1)
        and all(status == desired for status in f2p.values())
        and p2p_ok == len(expected["p2p"])
        and not unexpected_fail
    )
    return {
        "accepted_for_declared_control": accepted,
        "terminal_test_names": len(terminal),
        "multi_package_test_names": multi_package[:10],
        "conflicting_terminal_names": conflicting[:10],
        "repeated_package_test_pairs": repeated_pair[:10],
        "malformed_lines": malformed,
        "f2p_status": f2p,
        "p2p_passed": p2p_ok,
        "p2p_expected": len(expected["p2p"]),
        "unexpected_fail_count": len(unexpected_fail),
        "unexpected_fail_examples": unexpected_fail[:5],
    }


def negative_parser_checks(log: str, expected: dict) -> dict:
    lines = log.splitlines()
    chosen = expected["f2p"][0]
    removed = False
    dropped = []
    for line in lines:
        event = json.loads(line)
        if (
            not removed
            and event.get("Test") == chosen
            and event.get("Action") == "pass"
        ):
            removed = True
            continue
        dropped.append(line)
    if not removed:
        return {"required_event_found": False}
    conflict = json.dumps(
        {"Action": "fail", "Package": "audit.synthetic", "Test": chosen}
    )
    return {
        "required_event_found": True,
        "missing_required_event_rejected": not score(
            "\n".join(dropped), 0, expected, "gold"
        )["accepted_for_declared_control"],
        "conflicting_duplicate_rejected": not score(
            log + "\n" + conflict, 0, expected, "gold"
        )["accepted_for_declared_control"],
        "malformed_line_rejected": not score(log + "\n{", 0, expected, "gold")[
            "accepted_for_declared_control"
        ],
    }


def run_control(
    name: str,
    view: Path,
    operator: Path,
    output: Path,
    image: str,
    mount: str,
    expected: dict,
) -> dict:
    workspace = output / name
    if workspace.exists():
        raise ValueError(f"control workspace already exists: {workspace}")
    shutil.copytree(view, workspace, symlinks=False)
    if name == "gold":
        apply_patch(workspace, operator / "gold.diff")
    apply_patch(workspace, operator / "test.diff")
    if name == "wrong":
        gold_targets = patch_targets((operator / "gold.diff").read_bytes())
        source_path = next(
            (workspace / path for path in gold_targets if path.endswith(".go")), None
        )
        if source_path is None or not source_path.is_file():
            raise ValueError("no Go source for wrong-repair no-op")
        source_path.write_bytes(
            source_path.read_bytes() + b"\n// G3 wrong-repair no-op control\n"
        )
    cache = output / "cache"
    cache.mkdir(exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--network",
        "none",
        "--read-only",
        "--cpus",
        "2",
        "--memory",
        "2g",
        "--pids-limit",
        "256",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,exec,size=512m",
        "-e",
        "GOPROXY=off",
        "-e",
        "GOSUMDB=off",
        "-e",
        "GOCACHE=/g3-cache",
        "-v",
        f"{cache}:/g3-cache",
        "-v",
        f"{workspace}:{mount}:rw",
        "-w",
        mount,
        "--entrypoint",
        "go",
        image,
        "test",
        "-json",
        "./...",
    ]
    stdout_path = output / f"{name}.jsonl"
    stderr_path = output / f"{name}.stderr"
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            completed = subprocess.run(
                command, stdout=stdout, stderr=stderr, timeout=TIMEOUT_SECONDS
            )
        if (
            stdout_path.stat().st_size > MAX_LOG_BYTES
            or stderr_path.stat().st_size > MAX_LOG_BYTES
        ):
            raise ValueError("oracle output exceeds audit limit")
        raw = stdout_path.read_bytes()
        log = raw.decode("utf-8", errors="replace")
        summary = {
            "control": name,
            "exit_code": completed.returncode,
            "stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "stdout_bytes": len(raw),
            "stderr_bytes": stderr_path.stat().st_size,
            **score(log, completed.returncode, expected, name),
        }
        if name == "gold" and summary["accepted_for_declared_control"]:
            summary["negative_parser_checks"] = negative_parser_checks(log, expected)
        return summary
    except subprocess.TimeoutExpired:
        return {"control": name, "error": f"timeout_{TIMEOUT_SECONDS}_seconds"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("audit_dir", type=Path)
    parser.add_argument("packet")
    parser.add_argument(
        "image_digest", help="sha256: manifest digest of the published case image"
    )
    parser.add_argument(
        "container_workspace", help="absolute original image project path to overmount"
    )
    parser.add_argument(
        "--rescore-only",
        action="store_true",
        help="reparse existing logs without rerunning containers",
    )
    parser.add_argument("--round", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    candidate, expected = expected_row(args.source, args.packet)
    if not args.image_digest.startswith("sha256:") or len(args.image_digest) != 71:
        raise ValueError("image digest must be a complete SHA-256 manifest digest")
    if not args.container_workspace.startswith("/") or args.container_workspace == "/":
        raise ValueError("unsafe container workspace")
    image = expected["image"] + "@" + args.image_digest
    view = args.audit_dir / "workspaces" / args.packet
    operator = args.audit_dir / "operator" / args.packet
    suffix = "" if args.round == 1 else f"-repeat{args.round}"
    output = args.audit_dir / "controls" / f"{args.packet}{suffix}"
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    prior = (
        json.loads((output / "summary.json").read_text()) if args.rescore_only else None
    )
    for index, name in enumerate(("base", "gold", "wrong")):
        if prior is None:
            result = run_control(
                name, view, operator, output, image, args.container_workspace, expected
            )
        else:
            old = prior["controls"][index]
            raw = (output / f"{name}.jsonl").read_bytes()
            log = raw.decode("utf-8", errors="replace")
            result = {
                "control": name,
                "exit_code": old["exit_code"],
                "stdout_sha256": hashlib.sha256(raw).hexdigest(),
                "stdout_bytes": len(raw),
                **score(log, old["exit_code"], expected, name),
            }
            if name == "gold" and result["accepted_for_declared_control"]:
                result["negative_parser_checks"] = negative_parser_checks(log, expected)
        summaries.append(result)
        print(json.dumps({"packet": args.packet, **result}, sort_keys=True), flush=True)
        if result.get("error"):
            break
    summary_name = "summary-rescore.json" if args.rescore_only else "summary.json"
    (output / summary_name).write_text(
        json.dumps(
            {
                "source_id": candidate["instance_id"],
                "image": image,
                "controls": summaries,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
