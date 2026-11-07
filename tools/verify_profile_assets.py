"""Authenticate enrolled public assets with stdlib before install or product import."""

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import cast


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(assets: Path, controller: Path, target: str) -> dict[str, object]:
    if target not in {"linux-x86_64", "linux-aarch64", "macos-x86_64", "macos-aarch64"}:
        raise ValueError("invalid target")
    # Inspect trusted controller constants without executing it or importing any
    # candidate package. No installed dependency is part of this trust bootstrap.
    syntax = ast.parse(controller.read_text())
    values = [
        node.value
        for node in syntax.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(name, ast.Name) and name.id == "PINS" for name in node.targets
        )
    ]
    if len(values) != 1:
        raise ValueError("expected one enrolled pin map")
    value: object = ast.literal_eval(values[0])
    if not isinstance(value, dict):
        raise ValueError("unexpected enrolled asset set")
    pins = cast(dict[str, object], value)
    if set(pins) != {
        "release.json",
        "BOOTSTRAP_SHA256SUMS",
        "requirements.runtime.txt",
        "mos_eisley-0.1.0rc16-py3-none-any.whl",
    }:
        raise ValueError("unexpected enrolled asset set")
    for name, expected in pins.items():
        if (
            not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        ):
            raise ValueError("invalid enrolled digest")
        if (assets / name).stat().st_size > 64_000_000 or sha(
            assets / name
        ) != expected:
            raise ValueError("enrolled asset mismatch")
    payload = json.loads((assets / "release.json").read_bytes())["payload"]
    if (
        payload["version"] != "0.1.0-rc.16"
        or payload["source_commit"] != ("14eb79d52950f340aba159815222e04e6ea864e3")
        or payload["storage_epoch"] != 2
    ):
        raise ValueError("candidate identity mismatch")
    selected = next(a for a in payload["artifacts"] if a["platform"] == target)
    archive = assets / f"mos-0.1.0-rc.16-{target}.tar.gz"
    if archive.stat().st_size != selected["size"] or sha(archive) != selected["sha256"]:
        raise ValueError("candidate archive mismatch")
    bootstrap = assets / ("mos-install-" + target)
    if (
        f"{sha(bootstrap)}  {bootstrap.name}"
        not in (assets / "BOOTSTRAP_SHA256SUMS").read_text().splitlines()
    ):
        raise ValueError("bootstrap mismatch")
    return {
        "schema_version": 1,
        "passed": True,
        "target": target,
        "release_sha256": pins["release.json"],
        "candidate_imported": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--controller", type=Path, required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.assets, args.controller, args.target), sort_keys=True))
