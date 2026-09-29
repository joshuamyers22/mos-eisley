"""Rebuild or verify the bounded public G3 source-screening task views.

Run with: uvx --from duckdb==1.5.5 python tools/g3_candidate_task_views.py SOURCE
This tool creates no study assignments, labels, groups, or sampling receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb

SOURCE_SHA256 = "0e0bf9355f892ad74ae98d4e1c404f39fd6654a8e351ee3e6ab162e4a64cd3ad"
SOURCE_BYTES = 428_839_266
VIEW_VERSION = "g3-public-source-task-view-v1"
ROOT = Path(__file__).resolve().parents[1]
VIEW_DIR = ROOT / "docs" / "g3_candidate_task_views_v1"
FRAME_PATH = ROOT / "docs" / "G3_SWE_REBENCH_CANDIDATE_FRAME.json"

# Order is the SHA-256(instance_id) inspection order after the screen below and
# one-per-repository breadth cap. These identifiers are source metadata only.
INSPECTION_IDS = (
    "vaskoz__dailycodingproblem-go-178",
    "rsteube__carapace-273",
    "corneliusweig__ketall-98",
    "swaggest__rest-126",
    "palantir__policy-bot-220",
    "google__osv-scanner-16",
    "apache__camel-k-808",
    "mitchellh__mapstructure-194",
    "zegl__kube-score-294",
    "d5__tengo-221",
    "mgechev__revive-665",
    "magefile__mage-61",
)

# Human issue-content screen, performed before producing the packet bytes.
# These are review statuses, never oracle labels or sampling decisions.
REVIEW = {
    "vaskoz__dailycodingproblem-go-178": ("defer", "synthetic coding exercise"),
    "rsteube__carapace-273": ("candidate", "original issue text verified"),
    "corneliusweig__ketall-98": ("defer", "external screenshot and cluster context"),
    "swaggest__rest-126": ("defer", "mutable master branch links"),
    "palantir__policy-bot-220": ("candidate", "original issue text verified"),
    "google__osv-scanner-16": ("candidate", "original issue text verified"),
    "apache__camel-k-808": ("defer", "solution cause and PR discussion in issue"),
    "mitchellh__mapstructure-194": ("defer", "explicit fix and tests in issue"),
    "zegl__kube-score-294": ("defer", "external documentation dependency"),
    "d5__tengo-221": ("defer", "linked implementation branch"),
    "mgechev__revive-665": ("candidate", "original issue text verified"),
    "magefile__mage-61": ("defer", "linked source and ambiguous desired behavior"),
}

ISSUES = {
    "rsteube__carapace-273": (
        "rsteube/carapace",
        251,
        "LICENSE.txt",
        "298f0e2665e512a7d5053faf2ce4793c281efe6a",
    ),
    "palantir__policy-bot-220": (
        "palantir/policy-bot",
        168,
        "LICENSE",
        "8dada3edaf50dbc082c9a125058f25def75e625a",
    ),
    "google__osv-scanner-16": (
        "google/osv-scanner",
        7,
        "LICENSE",
        "d645695673349e3947e8e5ae42332d0ac3164cd7",
    ),
    "mgechev__revive-665": (
        "mgechev/revive",
        664,
        "LICENSE",
        "c617c7e0126bc1228a5064487aea14f10535cc2c",
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_digest(path: Path) -> tuple[int, str]:
    checksum = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            size += len(block)
            checksum.update(block)
    return size, checksum.hexdigest()


def added_lines(patch: str) -> set[str]:
    return {
        line[1:].strip()
        for line in patch.splitlines()
        if line.startswith("+")
        and not line.startswith("+++")
        and 40 <= len(line[1:].strip()) <= 300
    }


def screen(rows: list[tuple]) -> list[tuple]:
    matched = []
    for row in rows:
        ident, _, _, license_name, statement, patch, tests, f2p, p2p, cmd = row
        if license_name not in {
            "MIT",
            "Apache-2.0",
            "BSD-3-Clause",
            "BSD-2-Clause",
            "ISC",
        }:
            continue
        if not statement or not patch or not tests or cmd != "go test -v ./...":
            continue
        if not 1 <= len(f2p or []) <= 5 or len(p2p or []) > 200:
            continue
        if len(statement) > 3000 or len(patch) > 20000 or len(tests) > 20000:
            continue
        if any(line in statement for line in added_lines(patch) | added_lines(tests)):
            continue
        matched.append(row)
    matched.sort(key=lambda row: (digest(row[0].encode()), row[0]))
    return matched


def output_bytes(source: Path) -> dict[Path, bytes]:
    size, checksum = source_digest(source)
    if (size, checksum) != (SOURCE_BYTES, SOURCE_SHA256):
        raise ValueError("source byte count or SHA-256 differs from pinned release")
    connection = duckdb.connect()
    rows = connection.execute(
        """SELECT instance_id, repo, base_commit, license, problem_statement,
                  patch, test_patch, FAIL_TO_PASS, PASS_TO_PASS,
                  install_config.test_cmd
           FROM read_parquet(?) WHERE language = 'go'""",
        [str(source)],
    ).fetchall()
    matched = screen(rows)
    if len(matched) != 453 or len({row[1] for row in matched}) != 107:
        raise ValueError("source screen count drift")
    inspected = []
    seen_repos = set()
    for row in matched:
        if row[1] in seen_repos:
            continue
        seen_repos.add(row[1])
        inspected.append(row)
        if len(inspected) == 12:
            break
    if tuple(row[0] for row in inspected) != INSPECTION_IDS:
        raise ValueError("inspection batch drift")
    if set(REVIEW) != set(INSPECTION_IDS):
        raise ValueError("incomplete review disposition")
    files = {}
    frame_rows = []
    packet_number = 0
    for row in inspected:
        ident, repo, base, license_name, statement, _, _, _, _, _ = row
        status, reason = REVIEW[ident]
        item = {
            "instance_id": ident,
            "repo": repo,
            "base_commit": base,
            "license_metadata": license_name,
            "review_status": status,
            "review_reason": reason,
        }
        if status == "candidate":
            packet_number += 1
            issue_repo, issue_number, license_path, license_blob = ISSUES[ident]
            if repo != issue_repo:
                raise ValueError("issue repository mismatch")
            packet_path = VIEW_DIR / f"packet-{packet_number:03}.json"
            packet = {"schema_version": VIEW_VERSION, "task_text": statement}
            packet_bytes = (
                json.dumps(
                    packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                + "\n"
            ).encode()
            files[packet_path] = packet_bytes
            item.update(
                {
                    "original_issue_url": f"https://github.com/{repo}/issues/{issue_number}",
                    "license_path_at_base": license_path,
                    "license_blob_sha1_at_base": license_blob,
                    "packet_path": str(packet_path.relative_to(ROOT)),
                    "packet_sha256": digest(packet_bytes),
                    "source_statement_sha256": digest(statement.encode()),
                }
            )
        frame_rows.append(item)
    if packet_number != 4 or set(ISSUES) != {
        row["instance_id"] for row in frame_rows if row["review_status"] == "candidate"
    }:
        raise ValueError("candidate packet count or mapping drift")
    frame = {
        "schema_version": "g3-public-source-screen-v1",
        "authority": (
            "source screening only; no enrollment, assignment, sampling, label, "
            "split, or oracle claim"
        ),
        "source_sha256": SOURCE_SHA256,
        "source_bytes": SOURCE_BYTES,
        "screened_row_count": len(matched),
        "screened_repository_name_count": len({row[1] for row in matched}),
        "inspection_rule": (
            "sha256(instance_id) ascending; first row per repository name; cap 12"
        ),
        "inspected_rows": frame_rows,
    }
    files[FRAME_PATH] = (
        json.dumps(frame, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="pinned public Parquet file")
    parser.add_argument(
        "--write", action="store_true", help="write exact frame and packets"
    )
    args = parser.parse_args()
    expected = output_bytes(args.source)
    if VIEW_DIR.is_symlink():
        raise ValueError(f"refusing symlink task-view directory: {VIEW_DIR}")
    if args.write:
        VIEW_DIR.mkdir(parents=True, exist_ok=True)
        for path, data in expected.items():
            if path.is_symlink():
                raise ValueError(f"refusing symlink: {path}")
            path.write_bytes(data)
    for path, data in expected.items():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != data:
            raise ValueError(f"artifact differs from pinned source: {path}")
    if {path.name for path in VIEW_DIR.iterdir()} != {
        path.name for path in expected if path.parent == VIEW_DIR
    }:
        raise ValueError("unexpected file in task-view directory")
    print(f"verified {len(expected) - 1} task packets and one source-screening frame")


if __name__ == "__main__":
    main()
