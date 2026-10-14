"""Guard draft uploads and publish only the complete qualified asset inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

ASSET_PATTERNS = (
    "*.whl",
    "*.tar.gz",
    "release-sbom.cdx.json",
    "SOURCE_COMMIT",
    "SHA256SUMS",
    "standalone/mos-*.tar.gz",
    "standalone/mos-install-*",
    "standalone/release.json",
    "standalone/install.sh",
    "standalone/BOOTSTRAP_SHA256SUMS",
    "managers/*.rb",
    "qualification/*/*.json",
)
Api = Callable[[list[str]], object]


def mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid GitHub response object")
    if not all(isinstance(k, str) for k in cast(dict[object, object], value)):
        raise ValueError("invalid GitHub response object")
    return cast(dict[str, object], value)


def pages(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError("invalid paginated GitHub response")
    result: list[dict[str, object]] = []
    for page in cast(list[object], value):
        if not isinstance(page, list):
            raise ValueError("invalid GitHub response page")
        result.extend(mapping(item) for item in cast(list[object], page))
    return result


def github_api(arguments: list[str]) -> object:
    result = subprocess.run(
        [
            "gh",
            "api",
            "--hostname",
            "github.com",
            "-H",
            "X-GitHub-Api-Version: 2026-03-10",
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return cast(object, json.loads(result.stdout))


def inventory(root: Path, commit: str) -> dict[str, tuple[int, str]]:
    source = root / "SOURCE_COMMIT"
    if source.is_symlink() or not source.is_file():
        raise ValueError("unsafe or missing publication source record")
    if source.read_text().strip() != commit:
        raise ValueError("publication artifacts have a different source commit")
    result: dict[str, tuple[int, str]] = {}
    for pattern in ASSET_PATTERNS:
        files = sorted(root.glob(pattern))
        if not files:
            raise ValueError(f"missing required publication assets: {pattern}")
        for path in files:
            if path.is_symlink() or not path.is_file() or path.name in result:
                raise ValueError("unsafe or duplicate publication asset name")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            result[path.name] = (path.stat().st_size, f"sha256:{digest}")
    return result


def verify_subject(repo: str, tag: str, commit: str, api: Api) -> None:
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid publication repository")
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-rc\.\d+)?", tag):
        raise ValueError("invalid publication version tag")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("invalid publication source commit")
    # Reading repository immutability settings requires Administration permission.
    # The protected owner review checks that setting; this contents-only token
    # verifies the immutable publication response instead of acquiring admin access.
    ref = mapping(api([f"repos/{repo}/git/ref/tags/{tag}"]))
    target = mapping(ref.get("object"))
    for _ in range(5):
        if target.get("type") == "commit" and target.get("sha") == commit:
            return
        sha = target.get("sha")
        if target.get("type") != "tag" or not isinstance(sha, str):
            break
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            break
        target = mapping(mapping(api([f"repos/{repo}/git/tags/{sha}"])).get("object"))
    raise ValueError("publication tag does not resolve to the qualified source commit")


def verify_draft(release: dict[str, object], tag: str, commit: str) -> None:
    if release.get("draft") is not True:
        raise ValueError("already-published release cannot be changed")
    if release.get("tag_name") != tag or release.get("target_commitish") != commit:
        raise ValueError("draft release has a different tag or source commit")
    if release.get("prerelease") is not ("-rc." in tag):
        raise ValueError("draft release has a different preview/stable classification")


def verify_assets(
    assets: list[dict[str, object]],
    expected: dict[str, tuple[int, str]],
    *,
    complete: bool,
) -> None:
    seen: set[str] = set()
    for asset in assets:
        name = asset.get("name")
        if not isinstance(name, str) or name not in expected or name in seen:
            raise ValueError("unexpected or duplicate uploaded release asset")
        seen.add(name)
        size, digest = expected[name]
        if (
            asset.get("state") != "uploaded"
            or type(asset.get("size")) is not int
            or asset.get("size") != size
            or asset.get("digest") != digest
        ):
            raise ValueError(
                f"uploaded release asset differs from qualified bytes: {name}"
            )
    if complete and seen != set(expected):
        raise ValueError("draft release is missing qualified assets")


def preflight(repo: str, tag: str, commit: str, root: Path, api: Api) -> None:
    expected = inventory(root, commit)
    verify_subject(repo, tag, commit, api)
    releases = pages(api([f"repos/{repo}/releases", "--paginate", "--slurp"]))
    matches = [release for release in releases if release.get("tag_name") == tag]
    if len(matches) > 1:
        raise ValueError("multiple releases match the publication tag")
    if matches:
        release = matches[0]
        verify_draft(release, tag, commit)
        release_id = release.get("id")
        if type(release_id) is not int or release_id <= 0:
            raise ValueError("invalid draft release ID")
        assets = pages(
            api([f"repos/{repo}/releases/{release_id}/assets", "--paginate", "--slurp"])
        )
        verify_assets(assets, expected, complete=False)


def finalize(
    repo: str, tag: str, commit: str, root: Path, release_id: int, api: Api
) -> None:
    if release_id <= 0:
        raise ValueError("invalid draft release ID")
    expected = inventory(root, commit)
    verify_subject(repo, tag, commit, api)
    endpoint = f"repos/{repo}/releases/{release_id}"
    release = mapping(api([endpoint]))
    if release.get("id") != release_id:
        raise ValueError("GitHub returned a different release ID")
    verify_draft(release, tag, commit)
    assets = pages(api([f"{endpoint}/assets", "--paginate", "--slurp"]))
    verify_assets(assets, expected, complete=True)
    published = mapping(
        api(
            [
                endpoint,
                "--method",
                "PATCH",
                "-F",
                "draft=false",
                "-f",
                f"tag_name={tag}",
                "-f",
                f"target_commitish={commit}",
            ]
        )
    )
    if (
        published.get("id") != release_id
        or published.get("tag_name") != tag
        or published.get("target_commitish") != commit
        or published.get("prerelease") is not ("-rc." in tag)
        or published.get("draft") is not False
        or published.get("immutable") is not True
    ):
        raise ValueError("GitHub did not confirm the expected immutable publication")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "finalize"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--artifacts", type=Path, default=Path("dist"))
    parser.add_argument("--release-id", type=int)
    args = parser.parse_args()
    if args.action == "preflight":
        preflight(args.repo, args.tag, args.commit, args.artifacts, github_api)
    else:
        if args.release_id is None:
            parser.error("finalize requires --release-id")
        finalize(
            args.repo,
            args.tag,
            args.commit,
            args.artifacts,
            args.release_id,
            github_api,
        )
    print(f"Release {args.tag}: {args.action} passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
