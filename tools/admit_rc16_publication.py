"""Admit the exact retained rc.16 software and separately qualified receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import cast

from mos_eisley.app_release import parse_release
from tools.publish_app_release import Api, github_api, inventory, mapping

SOURCE = "14eb79d52950f340aba159815222e04e6ea864e3"
HARNESS = "e2faad64005e125043c16759d5b50d9d0378edb7"
TAG = "v0.1.0-rc.16"
TAG_OBJECT = "cdcb8240b84de4d909d345e35a08654064763535"
REPO = "repos/joshuamyers22/mos-eisley"
TARGETS = {
    "ubuntu-22.04": "linux-x86_64",
    "ubuntu-22.04-arm": "linux-aarch64",
    "macos-15": "macos-aarch64",
    "macos-15-intel": "macos-x86_64",
}
BINDINGS = {
    "publication-assets.json": (
        "cf40dd135b2ac3b0ddf5e9f96539cb8b43e90a89897599e28f79c6fc0cab9405"
    ),
    "signed-receipt-review.json": (
        "263b18160f863492c6f723f2b3f56d9331ec05fd4385b577c5b8a8e87894d02f"
    ),
    "signed-discovery-review.json": (
        "74fa37ff2de7c47a055958a92b1279c6dc167ac23496cc8b7fbf198edaa80386"
    ),
    "staged-startup.json": (
        "44b1e1dfa94c153d3b67ae7d454259b48cc2cc70d303b4ea0da4e8089eabb069"
    ),
}


def require(condition: object, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def sha(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), "unsafe evidence file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path: Path) -> object:
    require(path.stat().st_size <= 2 * 1024 * 1024, "oversized evidence")
    return cast(object, json.loads(path.read_text()))


def rows(value: object) -> list[dict[str, object]]:
    require(isinstance(value, list), "expected record list")
    return [mapping(v) for v in cast(list[object], value)]


def validate_runs(api: Api) -> None:
    """No cancelled or skipped required case is silently admitted as success."""
    original = {
        "gitleaks": "success",
        "prepare": "success",
        "publish": "skipped",
        "standalone / sbom-coverage": "success",
        **{f"standalone / standalone ({os_name})": "success" for os_name in TARGETS},
        **{
            f"qualify-signed ({os_name})": (
                "cancelled" if os_name == "macos-15-intel" else "success"
            )
            for os_name in TARGETS
        },
    }
    recovery = {
        "offline": "success",
        "discovery": "skipped",
        **{
            f"intel-recovery ({i})": "failure" if i == 0 else "success"
            for i in range(4)
        },
    }
    diagnostic = {
        "offline": "success",
        "diagnostic": "success",
        "intel-qualification": "skipped",
        "discovery": "skipped",
    }
    final = {
        "offline": "success",
        "diagnostic": "skipped",
        "intel-qualification": "success",
        **{f"discovery ({o}, {t})": "success" for o, t in TARGETS.items()},
    }
    specifications = (
        (42102119299, SOURCE, TAG, 350992511, "push", "cancelled", original),
        (
            42233939365,
            "efba0d4781f0e5e4dd3c3cfa9e2b9efe31aa9d3c",
            "test/rc16-intel-recovery",
            408617556,
            "workflow_dispatch",
            "failure",
            recovery,
        ),
        (
            42246992124,
            HARNESS,
            "test/rc16-startup-diagnostics",
            408617556,
            "workflow_dispatch",
            "success",
            diagnostic,
        ),
        (
            42282492215,
            HARNESS,
            "test/rc16-startup-diagnostics",
            408617556,
            "workflow_dispatch",
            "success",
            final,
        ),
    )
    for number, source, branch, workflow, event, conclusion, expected in specifications:
        run = mapping(api([f"{REPO}/actions/runs/{number}"]))
        identity = (
            run.get("id"),
            run.get("head_sha"),
            run.get("head_branch"),
            run.get("workflow_id"),
            run.get("event"),
            run.get("run_attempt"),
            run.get("status"),
            run.get("conclusion"),
        )
        require(
            identity
            == (number, source, branch, workflow, event, 1, "completed", conclusion),
            "upstream run identity",
        )
        response = mapping(api([f"{REPO}/actions/runs/{number}/jobs?per_page=100"]))
        jobs = rows(response.get("jobs"))
        observed = {j.get("name"): j.get("conclusion") for j in jobs}
        require(
            len(jobs) == len(expected) and observed == expected, "upstream job matrix"
        )
        require(
            all(j.get("status") == "completed" for j in jobs), "unfinished upstream job"
        )
    annotations = rows(api([f"{REPO}/check-runs/127590446087/annotations"]))
    require(
        any(
            a.get("message")
            == "The job has exceeded the maximum execution time of 1h15m0s"
            and a.get("annotation_level") == "failure"
            for a in annotations
        ),
        "original timeout evidence missing",
    )
    pull = mapping(api([f"{REPO}/pulls/371"]))
    require(
        pull.get("merged") is True
        and mapping(pull.get("head")).get("sha")
        == "78dc47e88434b79f1fa4431728af7653e6995007",
        "qualification review not merged",
    )
    merge_sha = "4595957a822e4eaf7b7560c9c44820736c82cb8b"
    head_sha = "78dc47e88434b79f1fa4431728af7653e6995007"
    merge = mapping(api([f"{REPO}/git/commits/{merge_sha}"]))
    head = mapping(api([f"{REPO}/git/commits/{head_sha}"]))
    parents = rows(merge.get("parents"))
    require(
        merge.get("sha") == merge_sha
        and head.get("sha") == head_sha
        and len(parents) == 2
        and parents[1].get("sha") == head_sha
        and mapping(merge.get("tree")).get("sha")
        == mapping(head.get("tree")).get("sha")
        and isinstance(mapping(head.get("tree")).get("sha"), str),
        "reviewed merge graph changed",
    )
    main = mapping(
        mapping(api([f"{REPO}/compare/{merge_sha}...main"])).get("merge_base_commit")
    )
    require(main.get("sha") == merge_sha, "review merge absent from main")
    ref = mapping(mapping(api([f"{REPO}/git/ref/tags/{TAG}"])).get("object"))
    require(
        (ref.get("type"), ref.get("sha")) == ("tag", TAG_OBJECT), "frozen tag moved"
    )
    target = mapping(mapping(api([f"{REPO}/git/tags/{TAG_OBJECT}"])).get("object"))
    require(
        (target.get("type"), target.get("sha")) == ("commit", SOURCE),
        "tag source changed",
    )
    ancestor = mapping(
        mapping(api([f"{REPO}/compare/{SOURCE}...main"])).get("merge_base_commit")
    )
    require(ancestor.get("sha") == SOURCE, "frozen source absent from main")


def copy_reports(source: Path, destination: Path) -> None:
    require(source.is_dir() and not source.is_symlink(), "missing report directory")
    files = list(source.iterdir())
    require(
        files
        and all(
            p.is_file() and not p.is_symlink() and p.suffix == ".json" for p in files
        ),
        "unexpected report input",
    )
    destination.mkdir(parents=True, exist_ok=True)
    for path in files:
        target = destination / path.name
        require(not target.exists(), "duplicate qualification report")
        shutil.copyfile(path, target)


def assemble(inputs: Path, output: Path) -> None:
    require(not output.exists(), "admitted output already exists")
    shutil.copytree(inputs / "prepared", output)
    require(not (output / "qualification").exists(), "preparation contains reports")
    for runner in TARGETS:
        if runner != "macos-15-intel":
            copy_reports(
                inputs / f"original-{runner}", output / "qualification" / runner
            )
    intel = output / "qualification/macos-15-intel"
    for group in (1, 2, 3):
        copy_reports(inputs / "predecessors" / f"rc16-intel-recovery-{group}", intel)
    copy_reports(inputs / "final-intel", intel)


def validate_artifacts(output: Path, evidence: Path) -> dict[str, tuple[int, str]]:
    for name, digest in BINDINGS.items():
        require(sha(evidence / name) == digest, "reviewed evidence changed")
    base = mapping(read(evidence / "signed-receipt-review.json"))
    expected = {r["name"]: r["sha256"] for r in rows(base.get("reports"))}
    require(len(expected) == 62, "incomplete reviewed report set")
    actual: dict[str, str] = {}
    for path in (output / "qualification").glob("*/*.json"):
        require(path.name not in actual, "duplicate output report")
        actual[path.name] = sha(path)
    require(actual == expected, "qualification receipts differ from reviewed bytes")
    release = parse_release((output / "standalone/release.json").read_bytes())
    require(
        (release.source_commit, release.version, release.channel, release.storage_epoch)
        == (SOURCE, TAG[1:], "preview", 2),
        "signed candidate changed",
    )
    require(
        sha(output / "standalone/release.json")
        == "1882d3db109ebc3b6f0d5c84de8dec0eecde96a47da5f72ad444d133b30ea3bc",
        "signed metadata changed",
    )
    assets = inventory(output, SOURCE, version=TAG[1:])
    manifest = [
        {"name": n, "size": size, "digest": digest}
        for n, (size, digest) in sorted(assets.items())
    ]
    require(
        len(assets) == 80 and manifest == read(evidence / "publication-assets.json"),
        "publication software/inventory changed",
    )
    return assets


def validate_supplementary(inputs: Path, evidence: Path) -> None:
    require(
        sha(inputs / "diagnostic/staged-startup.json")
        == BINDINGS["staged-startup.json"],
        "diagnostic receipt changed",
    )
    review = mapping(read(evidence / "signed-discovery-review.json"))
    reports = rows(review.get("reports"))
    require(
        {r.get("platform") for r in reports} == set(TARGETS.values())
        and len(reports) == 4,
        "incomplete discovery review",
    )
    for row in reports:
        target = row["platform"]
        path = (
            inputs
            / "discovery"
            / f"rc16-discovery-{target}"
            / f"qualification-discovery-{target}.json"
        )
        require(sha(path) == row.get("receipt_sha256"), "discovery receipt changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify-admitted", action="store_true")
    args = parser.parse_args()
    require(
        os.environ.get("GITHUB_REF") == "refs/heads/main", "publication requires main"
    )
    evidence = Path("docs/qualification/rc16")
    validate_runs(github_api)
    if not args.verify_admitted:
        require(args.inputs is not None, "inputs required")
        assemble(args.inputs, args.output)
        validate_supplementary(args.inputs, evidence)
    assets = validate_artifacts(args.output, evidence)
    receipt = {
        "schema": 1,
        "status": "admitted",
        "source": SOURCE,
        "tag": TAG,
        "publication_controller": os.environ["GITHUB_SHA"],
        "publication_run": os.environ["GITHUB_RUN_ID"],
        "asset_count": len(assets),
        "base_reports": 62,
        "supplementary_discovery_reports": 4,
        "original_run_still_cancelled": True,
        "original_publisher_still_skipped": True,
        "signing_operations": 0,
        "provider_calls": 0,
    }
    marker = args.output / "publication-admission.json"
    if args.verify_admitted:
        require(read(marker) == receipt, "admission provenance changed")
    else:
        marker.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
