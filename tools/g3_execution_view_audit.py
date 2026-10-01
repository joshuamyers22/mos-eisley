"""Verify four pinned public base trees and build issue-only execution workspaces.

This is an operator-side source audit, not a sampling or study enrollment tool.
The caller supplies downloaded GitHub archives, commit objects, and recursive
root-tree objects. No network request, model call, or oracle run occurs here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

import duckdb
from g3_candidate_task_views import SOURCE_BYTES, SOURCE_SHA256, digest, source_digest

ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / "docs/G3_SWE_REBENCH_CANDIDATE_FRAME.json"
CASES = {
    "rsteube__carapace-273": "carapace",
    "palantir__policy-bot-220": "policy-bot",
    "google__osv-scanner-16": "osv-scanner",
    "mgechev__revive-665": "revive",
}
# These files are present in the authenticated source tree, but are not needed
# in the task workspace. The vendor tree is also removed by the source builder's
# policy-bot install recipe; retaining it adds unrelated third-party material.
EXCLUDED_VIEW_PATHS = {
    "mgechev__revive-665": {".docs-deploy-key.pem.enc"},
    "palantir__policy-bot-220": {"config/policy-bot.example.yml"},
}
EXCLUDED_VIEW_PREFIXES = {"palantir__policy-bot-220": ("vendor/",)}
MAX_FILES = 2_000
MAX_FILE_BYTES = 10_000_000
MAX_TREE_BYTES = 60_000_000
SENSITIVE_PATTERNS = {
    "private_key_pem": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "github_token": re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
}


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def verify_git_tree(entries: list[dict], root_sha: str) -> None:
    by_path: dict[str, dict] = {}
    for entry in entries:
        path = entry.get("path")
        if not isinstance(path, str) or path in by_path:
            raise ValueError("invalid or duplicate recursive Git tree path")
        parts = PurePosixPath(path).parts
        if not parts or any(part in {".", "..", ".git"} for part in parts):
            raise ValueError("unsafe recursive Git tree path")
        if entry.get("type") not in {"blob", "tree"}:
            raise ValueError("submodule or unsupported Git tree entry")
        by_path[path] = entry

    directories = {"": root_sha}
    directories.update(
        {
            path: entry["sha"]
            for path, entry in by_path.items()
            if entry["type"] == "tree"
        }
    )
    children: dict[str, list[tuple[str, dict]]] = {path: [] for path in directories}
    for path, entry in by_path.items():
        parent = path.rpartition("/")[0]
        if parent not in directories:
            raise ValueError("recursive Git tree omits a parent directory")
        children[parent].append((path.rpartition("/")[2], entry))
    for path in sorted(directories, key=lambda name: name.count("/"), reverse=True):
        content = bytearray()
        ordered = sorted(
            children[path],
            key=lambda item: (
                item[0].encode() + (b"/" if item[1]["type"] == "tree" else b"")
            ),
        )
        for name, entry in ordered:
            mode = format(int(entry["mode"], 8), "o").encode()
            content.extend(mode + b" " + name.encode() + b"\0")
            content.extend(bytes.fromhex(entry["sha"]))
        computed = hashlib.sha1(
            b"tree " + str(len(content)).encode() + b"\0" + content
        ).hexdigest()
        if computed != directories[path]:
            raise ValueError(f"recursive Git tree hash differs: {path or '<root>'}")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def case_rows(source: Path) -> dict[str, tuple[str, str, str]]:
    if source_digest(source) != (SOURCE_BYTES, SOURCE_SHA256):
        raise ValueError("source byte count or SHA-256 differs from pinned release")
    with duckdb.connect() as connection:
        rows = connection.execute(
            """SELECT instance_id, problem_statement, patch, test_patch
               FROM read_parquet(?) WHERE instance_id IN (?, ?, ?, ?)""",
            [str(source), *CASES],
        ).fetchall()
    if len(rows) != len(CASES) or {row[0] for row in rows} != set(CASES):
        raise ValueError("pinned case set differs from candidate frame")
    return {
        ident: (statement, patch, test_patch)
        for ident, statement, patch, test_patch in rows
    }


def archive_blobs(
    archive: Path, commit: dict, tree: dict, expected_commit: str
) -> dict[str, tuple[bytes, str]]:
    if commit.get("sha") != expected_commit:
        raise ValueError("GitHub commit object does not match pinned base")
    tree_sha = commit.get("tree", {}).get("sha")
    if tree.get("sha") != tree_sha or tree.get("truncated") is not False:
        raise ValueError("recursive Git tree is missing, truncated or wrong")
    entries = tree.get("tree")
    if not isinstance(entries, list):
        raise ValueError("recursive Git tree has no entry list")
    verify_git_tree(entries, tree_sha)
    expected: dict[str, dict] = {}
    for entry in entries:
        if entry.get("type") == "commit":
            raise ValueError("submodule requires separate source audit")
        if entry.get("type") == "blob":
            path = entry.get("path")
            if not isinstance(path, str) or path in expected:
                raise ValueError("invalid or duplicate Git tree path")
            expected[path] = entry
    if not 0 < len(expected) <= MAX_FILES:
        raise ValueError("unexpected Git blob count")

    found: dict[str, tuple[bytes, str]] = {}
    total_bytes = 0
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            parts = PurePosixPath(member.name).parts
            if len(parts) < 1 or not parts[0].endswith(expected_commit):
                raise ValueError("archive root does not bind to pinned base")
            if len(parts) == 1:
                if not member.isdir():
                    raise ValueError("archive root is not a directory")
                continue
            relative = PurePosixPath(*parts[1:])
            if relative.is_absolute() or any(
                part in {".", "..", ".git"} for part in relative.parts
            ):
                raise ValueError("archive path escapes or contains Git metadata")
            if member.isdir():
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise ValueError("archive has a link or unsupported entry")
            path = relative.as_posix()
            if path in found or path not in expected:
                raise ValueError("archive has extra or duplicate file")
            if member.size > MAX_FILE_BYTES:
                raise ValueError("archive file exceeds audit limit")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ValueError("archive member cannot be read")
            data = stream.read(MAX_FILE_BYTES + 1)
            total_bytes += len(data)
            if len(data) != member.size or total_bytes > MAX_TREE_BYTES:
                raise ValueError("archive content exceeds declared audit bounds")
            entry = expected[path]
            if entry.get("mode") not in {"100644", "100755"}:
                raise ValueError("unsupported Git file mode")
            if git_blob_sha1(data) != entry.get("sha"):
                raise ValueError(f"archive blob differs from pinned Git tree: {path}")
            found[path] = (data, entry["mode"])
    if set(found) != set(expected):
        raise ValueError("archive lacks pinned Git tree blobs")
    return found


def write_exact(path: Path, data: bytes) -> None:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError(f"refusing symlink output path: {path}")
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError(f"existing output differs from pinned input: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def scan_view(
    files: dict[str, bytes], packet: bytes, gold: str, tests: str, future_pr: str
) -> dict:
    visible = {**files, "<issue-packet>": packet}
    for name, pattern in SENSITIVE_PATTERNS.items():
        matches = [path for path, data in visible.items() if pattern.search(data)]
        if matches:
            raise ValueError(f"{name} signature in projected view: {matches[:3]}")
    future_pr_bytes = future_pr.encode()
    if any(future_pr_bytes in data for data in visible.values()):
        raise ValueError("future repair PR URL in projected view")
    overlap = {}
    for kind, patch in (("gold", gold), ("test", tests)):
        lines = {
            line[1:].strip().encode()
            for line in patch.splitlines()
            if line.startswith("+")
            and not line.startswith("+++")
            and 20 <= len(line[1:].strip()) <= 300
        }
        hits = {
            line: [path for path, data in files.items() if line in data]
            for line in lines
        }
        overlap[kind] = {
            "added_lines_screened": len(lines),
            "overlapping_lines": sum(bool(paths) for paths in hits.values()),
            "overlap_paths": sorted(
                {path for paths in hits.values() for path in paths}
            ),
        }
    return overlap


def workspace_digest(blobs: dict[str, tuple[bytes, str]], excluded: set[str]) -> str:
    checksum = hashlib.sha256()
    for path in sorted(set(blobs) - excluded):
        data, mode = blobs[path]
        name = path.encode()
        checksum.update(len(name).to_bytes(4, "big"))
        checksum.update(name)
        checksum.update(mode.encode() + b"\0")
        checksum.update(bytes.fromhex(digest(data)))
    return checksum.hexdigest()


def build(source: Path, archive_dir: Path, output_dir: Path) -> list[dict]:
    frame = load_json(FRAME)
    candidates = [
        row for row in frame["inspected_rows"] if row["review_status"] == "candidate"
    ]
    if len(candidates) != len(CASES) or {
        row["instance_id"] for row in candidates
    } != set(CASES):
        raise ValueError("candidate frame changed")
    rows = case_rows(source)
    results = []
    for candidate in candidates:
        ident = candidate["instance_id"]
        name = CASES[ident]
        base = candidate["base_commit"]
        statement, gold, tests = rows[ident]
        packet_path = ROOT / candidate["packet_path"]
        packet_bytes = packet_path.read_bytes()
        if digest(packet_bytes) != candidate["packet_sha256"]:
            raise ValueError("task packet hash differs from candidate frame")
        packet = json.loads(packet_bytes)
        if (
            set(packet) != {"schema_version", "task_text"}
            or packet["task_text"] != statement
        ):
            raise ValueError("task packet is not the pinned issue-only projection")
        blobs = archive_blobs(
            archive_dir / f"{name}.tar.gz",
            load_json(archive_dir / f"{name}.commit.json"),
            load_json(archive_dir / f"{name}.root-tree.json"),
            base,
        )
        packet_number = Path(candidate["packet_path"]).stem
        workspace = output_dir / "workspaces" / packet_number
        if workspace.is_symlink():
            raise ValueError("workspace directory is a symlink")
        workspace.mkdir(parents=True, exist_ok=True)
        excluded = {
            path
            for path in blobs
            if path in EXCLUDED_VIEW_PATHS.get(ident, set())
            or path.startswith(EXCLUDED_VIEW_PREFIXES.get(ident, ()))
        }
        if ident == "mgechev__revive-665" and excluded != {".docs-deploy-key.pem.enc"}:
            raise ValueError("revive encrypted-key exclusion drift")
        if ident == "palantir__policy-bot-220" and (
            "config/policy-bot.example.yml" not in excluded
            or not any(path.startswith("vendor/") for path in excluded)
        ):
            raise ValueError("policy-bot vendor exclusion drift")
        view_files = {
            path: data for path, (data, _) in blobs.items() if path not in excluded
        }
        future_pr = (
            f"https://github.com/{candidate['repo']}/pull/{ident.rsplit('-', 1)[1]}"
        )
        overlap = scan_view(view_files, packet_bytes, gold, tests, future_pr)
        for path, (data, mode) in blobs.items():
            if path in excluded:
                continue
            target = workspace / path
            write_exact(target, data)
            target.chmod(0o755 if mode == "100755" else 0o644)
        visible_paths = set(blobs) - excluded
        expected_dirs = {
            parent.as_posix()
            for path in visible_paths
            for parent in PurePosixPath(path).parents
            if parent.as_posix() != "."
        }
        entries = list(workspace.rglob("*"))
        if any(path.is_symlink() for path in entries):
            raise ValueError("workspace contains a symlink")
        actual_files = {
            path.relative_to(workspace).as_posix() for path in entries if path.is_file()
        }
        actual_dirs = {
            path.relative_to(workspace).as_posix() for path in entries if path.is_dir()
        }
        if actual_files != visible_paths or actual_dirs != expected_dirs:
            raise ValueError("workspace file or directory set differs")
        operator = output_dir / "operator" / packet_number
        write_exact(operator / "gold.diff", gold.encode())
        write_exact(operator / "test.diff", tests.encode())
        write_exact(operator / "task-packet.json", packet_bytes)
        results.append(
            {
                "packet": packet_number,
                "source_id": ident,
                "base_commit": base,
                "root_tree": load_json(archive_dir / f"{name}.commit.json")["tree"][
                    "sha"
                ],
                "archive_sha256": digest((archive_dir / f"{name}.tar.gz").read_bytes()),
                "files": len(blobs),
                "bytes": sum(len(data) for data, _ in blobs.values()),
                "view_files": len(blobs) - len(excluded),
                "view_exclusions": len(excluded),
                "view_digest": workspace_digest(blobs, excluded),
                "literal_overlap_scan": overlap,
                "workspace": str(workspace),
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("archive_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    if args.output_dir.is_symlink():
        raise ValueError("output directory is a symlink")
    print(json.dumps(build(args.source, args.archive_dir, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
