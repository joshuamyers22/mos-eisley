"""Build a native cask DMG; production requires real Apple trust checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from mos_eisley.app_release import platform_id

MACHO = {
    bytes.fromhex(value)
    for value in (
        "feedface",
        "cefaedfe",
        "feedfacf",
        "cffaedfe",
        "cafebabe",
        "bebafeca",
        "cafebabf",
        "bfbafeca",
    )
}


def run(*arguments: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments, check=True, capture_output=True, text=True, timeout=timeout
    )


def verify_signature(path: Path, team: str, *, runtime: bool) -> None:
    run("codesign", "--verify", "--strict", str(path))
    details = run("codesign", "-d", "--verbose=4", str(path)).stderr
    if (
        "Authority=Developer ID Application:" not in details
        or f"TeamIdentifier={team}\n" not in details
        or "Timestamp=" not in details
        or (runtime and not re.search(r"flags=0x[0-9a-f]+\([^\n]*\bruntime\b", details))
    ):
        raise ValueError(
            "Developer ID, expected team, secure timestamp or runtime missing"
        )
    if runtime:
        entitlements = run("codesign", "-d", "--entitlements", "-", str(path)).stdout
        if entitlements:
            values = plistlib.loads(entitlements.encode())
            if values.get("com.apple.security.get-task-allow"):
                raise ValueError("development task entitlement is forbidden")


def verify_image(path: Path, team: str) -> None:
    verify_signature(path, team, runtime=False)
    run("xcrun", "stapler", "validate", str(path))
    run(
        "spctl",
        "--assess",
        "--type",
        "open",
        "--context",
        "context:primary-signature",
        str(path),
    )


def validate_bundle(bundle: Path) -> list[Path]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("expected a real native bundle directory")
    native: list[Path] = []
    for path in bundle.rglob("*"):
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(bundle.resolve()):
                raise ValueError("bundle symlink escapes native payload")
        elif path.is_file():
            with path.open("rb") as stream:
                if stream.read(4) in MACHO:
                    native.append(path)
        elif not path.is_dir():
            raise ValueError("unsupported special file in native payload")
    if bundle / "mos" not in native:
        raise ValueError("bundle has no native mos executable")
    return native


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("dist/cask"))
    parser.add_argument("--development", action="store_true")
    parser.add_argument(
        "--identity", help="Developer ID Application certificate identity"
    )
    parser.add_argument("--team-id")
    parser.add_argument(
        "--notary-profile", help="Existing notarytool keychain profile name"
    )
    args = parser.parse_args()
    target = platform_id()
    if not target.startswith("macos-"):
        parser.error("cask DMGs require a native macOS host")
    if args.development:
        if args.identity or args.team_id or args.notary_profile:
            parser.error("development fixtures cannot use production signing options")
    elif (
        not args.identity
        or not args.notary_profile
        or not re.fullmatch(r"[A-Z0-9]{10}", args.team_id or "")
    ):
        parser.error(
            "production requires Developer ID identity, team ID and notary profile"
        )
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    source = run("git", "rev-parse", "HEAD").stdout.strip()
    if not args.development and run("git", "status", "--porcelain").stdout:
        raise ValueError("production requires an unchanged source checkout")
    if not args.development:
        tagged = run(
            "git", "rev-parse", f"refs/tags/v{version}^{{commit}}"
        ).stdout.strip()
        if tagged != source:
            raise ValueError(
                "production requires a new exact version tag, not an old release"
            )
        run("git", "merge-base", "--is-ancestor", source, "refs/remotes/origin/main")
    native = validate_bundle(args.bundle)
    actual_version = run(str(args.bundle.resolve() / "mos"), "--version").stdout.strip()
    if actual_version != f"mos-eisley {version}":
        raise ValueError("native payload version differs from project metadata")
    if not args.development:
        identities = run("security", "find-identity", "-v", "-p", "codesigning").stdout
        if (
            args.identity not in identities
            or "Developer ID Application:" not in identities
        ):
            raise ValueError("requested Developer ID identity is unavailable")
        for path in native:
            verify_signature(path, args.team_id, runtime=True)
    args.output.mkdir(parents=True, exist_ok=True)
    suffix = "-development" if args.development else ""
    image = args.output.resolve() / f"mos-{version}-{target}-cask{suffix}.dmg"
    receipt = image.with_suffix(".json")
    if image.exists() or receipt.exists():
        raise ValueError("refusing to replace an existing cask candidate")
    with tempfile.TemporaryDirectory(prefix="mos-cask-payload-") as temporary:
        payload = Path(temporary)
        application = payload / "Mos Eisley"
        shutil.copytree(args.bundle, application, symlinks=True)
        shutil.copyfile("LICENSE", application / "LICENSE")
        (application / "installation-origin.json").write_text(
            json.dumps({"origin": "homebrew-cask"}) + "\n"
        )
        run(
            "hdiutil",
            "create",
            "-volname",
            "Mos Eisley",
            "-srcfolder",
            str(payload),
            "-format",
            "UDZO",
            str(image),
            timeout=300,
        )
    notarization: dict[str, object] | None = None
    if not args.development:
        run("codesign", "--sign", args.identity, "--timestamp", str(image))
        notarization = json.loads(
            run(
                "xcrun",
                "notarytool",
                "submit",
                str(image),
                "--keychain-profile",
                args.notary_profile,
                "--wait",
                "--timeout",
                "20m",
                "--output-format",
                "json",
                timeout=1300,
            ).stdout
        )
        if notarization is None or notarization.get("status") != "Accepted":
            raise ValueError("Apple notarization did not accept the candidate")
        run("xcrun", "stapler", "staple", str(image))
        verify_image(image, args.team_id)
    receipt.write_text(
        json.dumps(
            {
                "schema": 1,
                "version": version,
                "source_commit": source,
                "platform": target,
                "file": image.name,
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "size": image.stat().st_size,
                "development": args.development,
                "team_id": args.team_id,
                "notarization": notarization,
                "apple_trust_verified": not args.development,
                "native_macho_count": len(native),
                "publication_authorized": False,
            },
            sort_keys=True,
        )
        + "\n"
    )
    print(image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
