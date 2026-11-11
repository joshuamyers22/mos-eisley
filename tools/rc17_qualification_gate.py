"""Read-only admission for the exact rc.17 Intel runner-timeout continuation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

SOURCE = "e6b1d75cc4140b7fb31c4a7a36fcdaf931c8f481"
TIMEOUT = "The job has exceeded the maximum execution time of 1h15m0s"
SIGNED = {
    129463949571: ("qualify-signed (ubuntu-22.04-arm)", "success"),
    129463949519: ("qualify-signed (ubuntu-22.04)", "success"),
    129463949536: ("qualify-signed (macos-15)", "success"),
    129463949538: ("qualify-signed (macos-15-intel)", "cancelled"),
}
REPLAY = {
    129463949717: ("qualify-replay (ubuntu-22.04-arm)", "success"),
    129463949915: ("qualify-replay (ubuntu-22.04)", "success"),
    129463949658: ("qualify-replay (macos-15)", "success"),
    129463949605: ("qualify-replay (macos-15-intel)", "success"),
}


def admitted(run: object, jobs: object, annotations: object) -> bool:
    """Refuse incomplete, substituted or non-timeout original runs."""
    if not isinstance(run, dict) or not isinstance(jobs, dict):
        return False
    run = cast(dict[str, object], run)
    jobs = cast(dict[str, object], jobs)
    expected = {
        "id": 42685881830,
        "head_sha": SOURCE,
        "head_branch": "v0.1.0-rc.17",
        "event": "push",
        "workflow_id": 350992511,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "cancelled",
    }
    if any(run.get(k) != v for k, v in expected.items()):
        return False
    rows = jobs.get("jobs")
    if not isinstance(rows, list):
        return False
    values = cast(list[object], rows)
    if not all(isinstance(j, dict) for j in values):
        return False
    rows = cast(list[dict[str, object]], values)
    prepared = [j for j in rows if j.get("name") == "prepare"]
    signed = [j for j in rows if str(j.get("name", "")).startswith("qualify-signed")]
    if len(prepared) != 1 or len(signed) != 4:
        return False
    if (prepared[0].get("id"), prepared[0].get("conclusion")) != (
        129396540859,
        "success",
    ):
        return False
    if not all(isinstance(j.get("id"), int) for j in signed):
        return False
    if {cast(int, j.get("id")) for j in signed} != set(SIGNED):
        return False
    for j in signed:
        if (j.get("name"), j.get("conclusion")) != SIGNED[cast(int, j["id"])]:
            return False
    for expected_name, expected_id, expected_conclusion in (
        *((name, job_id, conclusion) for job_id, (name, conclusion) in REPLAY.items()),
        ("publish", 129503118942, "skipped"),
    ):
        found = [j for j in rows if j.get("name") == expected_name]
        if len(found) != 1 or (found[0].get("id"), found[0].get("conclusion")) != (
            expected_id,
            expected_conclusion,
        ):
            return False
    if not isinstance(annotations, list):
        return False
    for item in cast(list[object], annotations):
        if isinstance(item, dict):
            a = cast(dict[str, object], item)
            if a.get("annotation_level") == "failure" and a.get("message") == TIMEOUT:
                return True
    return False


def main() -> None:
    root = Path(".work")
    values = [
        json.loads((root / name).read_text())
        for name in (
            "protected-run.json",
            "protected-jobs.json",
            "timeout-annotations.json",
        )
    ]
    if not admitted(*values):
        raise SystemExit("Frozen rc.17 timeout continuation refused")
    print("Exact frozen preparation and original Intel timeout admitted")


if __name__ == "__main__":
    main()
