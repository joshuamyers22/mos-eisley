"""Generate a reviewable cask from two exact, validated native DMGs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from tools.build_macos_cask import verify_image

ORIGIN = "https://github.com/joshuamyers22/mos-eisley/releases/download/"
PLATFORMS = {"macos-aarch64", "macos-x86_64"}


@dataclass(frozen=True)
class Package:
    version: str
    source: str
    platform: str
    image: Path
    sha256: str
    team: str | None


@dataclass(frozen=True)
class Identity:
    version: str
    source: str
    team: str


def mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid cask receipt object")
    return cast(dict[str, object], value)


def load_package(
    receipt: Path, *, development: bool, expected_team: str | None = None
) -> Package:
    if receipt.is_symlink() or not receipt.is_file():
        raise ValueError("unsafe or missing cask receipt")
    raw = mapping(json.loads(receipt.read_text()))
    if raw.get("schema") != 1:
        raise ValueError("invalid cask receipt")
    version, source, target = (
        raw.get("version"),
        raw.get("source_commit"),
        raw.get("platform"),
    )
    if (
        not isinstance(version, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+(?:-rc\.\d+)?", version)
        or not isinstance(source, str)
        or not re.fullmatch(r"[0-9a-f]{40}", source)
        or not isinstance(target, str)
        or target not in PLATFORMS
    ):
        raise ValueError("invalid cask version, source or platform")
    suffix = "-development" if development else ""
    name = f"mos-{version}-{target}-cask{suffix}.dmg"
    image = receipt.parent / name
    if (
        raw.get("development") is not development
        or raw.get("file") != name
        or image.is_symlink()
        or not image.is_file()
        or type(raw.get("size")) is not int
        or image.stat().st_size != raw["size"]
        or hashlib.sha256(image.read_bytes()).hexdigest() != raw.get("sha256")
    ):
        raise ValueError("cask image identity or development mode mismatch")
    team = raw.get("team_id")
    if team is not None and not isinstance(team, str):
        raise ValueError("invalid Apple team")
    checksum = raw.get("sha256")
    if not isinstance(checksum, str):
        raise ValueError("invalid cask checksum")
    if not development:
        if not expected_team or team != expected_team:
            raise ValueError("Apple team differs from trusted publisher selection")
        notarization = mapping(raw.get("notarization"))
        if (
            raw.get("apple_trust_verified") is not True
            or not isinstance(team, str)
            or not re.fullmatch(r"[A-Z0-9]{10}", team)
            or notarization.get("status") != "Accepted"
        ):
            raise ValueError(
                "cask requires accepted notarization and Apple trust evidence"
            )
        # Do not promote JSON assertions alone: reassess both actual images.
        verify_image(image, team)
    return Package(version, source, target, image, checksum, team)


def generate(
    artifacts: Path, *, development: bool, identity: Identity | None = None
) -> str:
    if not development and identity is None:
        raise ValueError(
            "production requires an independently selected release identity"
        )
    packages = [
        load_package(
            path,
            development=development,
            expected_team=identity.team if identity else None,
        )
        for path in artifacts.glob("*.json")
    ]
    if len(packages) != 2 or {p.platform for p in packages} != PLATFORMS:
        raise ValueError("both unique native macOS architectures are required")
    if len({(p.version, p.source, p.team) for p in packages}) != 1:
        raise ValueError("mixed cask versions, source commits or Apple teams")
    if identity is not None and any(
        (p.version, p.source, p.team)
        != (identity.version, identity.source, identity.team)
        for p in packages
    ):
        raise ValueError("cask differs from selected version, source or Apple team")
    by_platform = {p.platform: p for p in packages}
    arm, intel = by_platform["macos-aarch64"], by_platform["macos-x86_64"]
    suffix = "-development" if development else ""
    base = (
        artifacts.resolve().as_uri() + "/"
        if development
        else ORIGIN + f"v{arm.version}/"
    )
    lines = [
        "# Generated cask candidate; publisher/owner review is still required.",
        'cask "mos-eisley" do',
        '  arch arm: "aarch64", intel: "x86_64"',
        "",
        f'  version "{arm.version}"',
        f'  sha256 arm:   "{arm.sha256}",',
        f'         intel: "{intel.sha256}"',
        "",
        f'  url "{base}mos-#{{version}}-macos-#{{arch}}-cask{suffix}.dmg"',
        '  name "Mos Eisley"',
        '  desc "Multi-provider coding and review terminal"',
        '  homepage "https://github.com/joshuamyers22/mos-eisley"',
        "",
        "  livecheck do",
        '    skip "Owner-reviewed immutable releases"',
        "  end",
    ]
    if development:
        lines.extend(
            [
                "",
                '  disable! date: "2026-10-15", '
                'because: "is an unsigned development fixture"',
            ]
        )
    lines.extend(
        [
            "",
            "  depends_on macos: :sequoia",
            "",
            '  binary "Mos Eisley/mos"',
        ]
    )
    if "-rc." in arm.version:
        lines.extend(
            [
                "",
                '  caveats "Preview channel. Close Mos sessions before upgrading."',
            ]
        )
    lines.extend(["end", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("dist/cask/Casks/mos-eisley.rb")
    )
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--team-id", help="Expected publisher Apple Team ID")
    args = parser.parse_args()
    identity = None
    if not args.development:
        if not re.fullmatch(r"[A-Z0-9]{10}", args.team_id or ""):
            parser.error("production requires the expected publisher --team-id")
        version = tomllib.loads(Path("pyproject.toml").read_text())["project"][
            "version"
        ]
        source = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        tagged = subprocess.check_output(
            ["git", "rev-parse", f"refs/tags/v{version}^{{commit}}"], text=True
        ).strip()
        if (
            source != tagged
            or subprocess.check_output(
                ["git", "status", "--porcelain"], text=True
            ).strip()
        ):
            parser.error("production requires the clean exact version-tag checkout")
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source, "refs/remotes/origin/main"],
            check=True,
        )
        identity = Identity(version, source, args.team_id)
    content = generate(args.artifacts, development=args.development, identity=identity)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
