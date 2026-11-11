"""Review-issued custody for rc.17 reports whose hidden provenance was omitted.

This does not recreate the missing controller receipt or qualify report contents.
It binds retained ZIP bytes to the exact successful Actions execution instead.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import cast

RUN = 42735189293
CONTROLLER = "c9fe9f5fb8ca0c9b04ec2608227b7abb98a48cb0"
SOURCE = "e6b1d75cc4140b7fb31c4a7a36fcdaf931c8f481"
JOBS = {
    129562582428: "offline",
    129562685339: "intel-continuation (0)",
    129562685291: "intel-continuation (1)",
    129562685419: "intel-continuation (2)",
}
ARTIFACTS = {
    0: (
        13727856445,
        "934557ccaeca61ddc01da909a8d45e65878984a5432ed340e735718a791a6b5e",
    ),
    1: (
        13727601738,
        "6890fa1344c82daf91935d91b6769d1db530a1071ef9a475c1db08b08be47456",
    ),
    2: (
        13727491954,
        "6558f3f185ba78851850192a837988af89a38d5c8b7422f425f79fb2b3eceb8a",
    ),
}
REPORTS = {
    0: {f"qualification-upgrade-rc{n}-macos-x86_64.json" for n in (12, 13)},
    1: {f"qualification-upgrade-rc{n}-macos-x86_64.json" for n in (14, 15)},
    2: {
        "qualification-upgrade-rc16-macos-x86_64.json",
        "qualification-progress-macos-15-intel.json",
        "qualification-homebrew-macos-15-intel.json",
    },
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def record(value: object) -> dict[str, object]:
    require(isinstance(value, dict), "Expected an object")
    return cast(dict[str, object], value)


def records(value: object) -> list[dict[str, object]]:
    require(isinstance(value, list), "Expected an array")
    return [record(v) for v in cast(list[object], value)]


def verify_zip(data: bytes, digest: str, expected: set[str]) -> dict[str, str]:
    """Hash exact ZIP and inspect allowlisted bounded files without extraction."""
    require(len(data) <= 1_000_000, "Oversized report archive")
    require(hashlib.sha256(data).hexdigest() == digest, "Artifact digest mismatch")
    paths = {"dist/standalone/" + name for name in expected}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        items = archive.infolist()
        require(len(items) == len(paths), "Unexpected or duplicate ZIP entries")
        require({p.filename for p in items} == paths, "Unexpected ZIP report paths")
        require(all(p.file_size <= 100_000 for p in items), "Oversized report")
        return {
            p.filename.rsplit("/", 1)[1]: hashlib.sha256(archive.read(p)).hexdigest()
            for p in items
        }


def review(root: Path) -> dict[str, object]:
    run = record(json.loads((root / "run.json").read_bytes()))
    expected_run = {
        "id": RUN,
        "head_sha": CONTROLLER,
        "workflow_id": 412761132,
        "path": ".github/workflows/rc17-signed-continuation.yml",
        "event": "pull_request",
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
    }
    require(
        all(run.get(k) == v for k, v in expected_run.items()), "Wrong continuation run"
    )
    jobs = records(record(json.loads((root / "jobs.json").read_bytes())).get("jobs"))
    require(len(jobs) == len(JOBS), "Unexpected continuation jobs")
    require({j.get("id") for j in jobs} == set(JOBS), "Wrong continuation job IDs")
    for job in jobs:
        require(job.get("name") == JOBS[cast(int, job["id"])], "Wrong job name")
        require(job.get("conclusion") == "success", "Continuation job did not pass")
    artifacts = records(
        record(json.loads((root / "artifacts.json").read_bytes())).get("artifacts")
    )
    require(len(artifacts) == 3, "Unexpected artifact inventory")
    reports: dict[str, object] = {}
    for group, (artifact_id, digest) in ARTIFACTS.items():
        found = [a for a in artifacts if a.get("id") == artifact_id]
        require(len(found) == 1, "Missing or duplicate artifact")
        artifact = found[0]
        require(
            artifact.get("name") == f"rc17-intel-continuation-{group}",
            "Wrong artifact name",
        )
        require(artifact.get("digest") == "sha256:" + digest, "Wrong recorded digest")
        require(artifact.get("expired") is False, "Expired artifact")
        origin = record(artifact.get("workflow_run"))
        require(
            origin.get("id") == RUN and origin.get("head_sha") == CONTROLLER,
            "Wrong artifact origin",
        )
        hashes = verify_zip(
            (root / f"group-{group}.zip").read_bytes(), digest, REPORTS[group]
        )
        for name, sha in hashes.items():
            reports[name] = dict(
                artifact_id=artifact_id, artifact_sha256=digest, sha256=sha, group=group
            )
    return dict(
        schema_version=1,
        status="verified_actions_artifact_custody",
        issuer="downstream_evidence_review",
        original_controller_receipt_retained=False,
        omission="hidden .work paths excluded by upload action",
        original_run=RUN,
        original_attempt=1,
        controller_source=CONTROLLER,
        candidate_source=SOURCE,
        reports=reports,
        provider_calls=0,
        qualification_contents_reviewed=False,
        publication_authorized=False,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = review(args.root)
    (args.root / "custody-review.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(
        "Exact successful Actions run and seven immutable report ZIP members verified"
    )


if __name__ == "__main__":
    main()
