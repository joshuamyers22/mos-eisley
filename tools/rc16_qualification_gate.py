"""Read-only admission for the exact rc.16 Intel runner-timeout continuation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

SOURCE = "14eb79d52950f340aba159815222e04e6ea864e3"
TIMEOUT = "The job has exceeded the maximum execution time of 1h15m0s"
SIGNED = {
    127590446002: ("qualify-signed (ubuntu-22.04-arm)", "success"),
    127590446094: ("qualify-signed (ubuntu-22.04)", "success"),
    127590446091: ("qualify-signed (macos-15)", "success"),
    127590446087: ("qualify-signed (macos-15-intel)", "cancelled"),
}


def admitted(run: object, jobs: object, annotations: object) -> bool:
    """Refuse incomplete, substituted or non-timeout original runs."""
    if not isinstance(run, dict) or not isinstance(jobs, dict):
        return False
    run = cast(dict[str, object], run)
    jobs = cast(dict[str, object], jobs)
    expected = {
        "id": 42102119299,
        "head_sha": SOURCE,
        "head_branch": "v0.1.0-rc.16",
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
        127516552543,
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
        raise SystemExit("Frozen rc.16 timeout continuation refused")
    print("Exact frozen preparation and original Intel timeout admitted")


if __name__ == "__main__":
    main()
