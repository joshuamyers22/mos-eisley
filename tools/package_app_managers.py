"""Generate npm and Homebrew packages from the exact signed shared release."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from mos_eisley.app_install import extract_archive
from mos_eisley.app_release import parse_release, verify_archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("dist/managers"))
    args = parser.parse_args()
    release = parse_release((args.artifacts / "release.json").read_bytes())
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    npm = output / "npm"
    npm.mkdir(exist_ok=True)
    dependencies: dict[str, str] = {}
    for artifact in release.artifacts:
        name = f"@mos-eisley/mos-eisley-{artifact.platform}"
        dependencies[name] = release.version
        package = npm / artifact.platform
        package.mkdir(exist_ok=True)
        runtime = package / "runtime"
        runtime.mkdir(exist_ok=True)
        raw = (
            args.artifacts / f"mos-{release.version}-{artifact.platform}.tar.gz"
        ).read_bytes()
        verify_archive(raw, artifact)
        extract_archive(raw, runtime)
        (runtime / "installation-origin.json").write_text(json.dumps({"origin": "npm"}))
        system, arch = artifact.platform.split("-")
        (package / "package.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version": release.version,
                    "license": "SEE LICENSE IN LICENSE",
                    "os": ["darwin" if system == "macos" else "linux"],
                    "cpu": ["arm64" if arch == "aarch64" else "x64"],
                    "files": ["runtime", "LICENSE"],
                    "repository": "github:joshuamyers22/mos-eisley",
                },
                indent=2,
            )
        )
        shutil.copyfile("LICENSE", package / "LICENSE")
    main_package = npm / "main"
    main_package.mkdir(exist_ok=True)
    shutil.copyfile("distribution/npm/launcher.cjs", main_package / "launcher.cjs")
    (main_package / "launcher.cjs").chmod(0o755)
    shutil.copyfile("LICENSE", main_package / "LICENSE")
    (main_package / "package.json").write_text(
        json.dumps(
            {
                "name": "@mos-eisley/mos-eisley",
                "version": release.version,
                "license": "SEE LICENSE IN LICENSE",
                "bin": {"mos": "launcher.cjs"},
                "engines": {"node": ">=22"},
                "files": ["launcher.cjs", "LICENSE"],
                "optionalDependencies": dependencies,
                "repository": "github:joshuamyers22/mos-eisley",
            },
            indent=2,
        )
    )
    formula: list[str] = [
        "# Generated from verified release.json; do not edit checksums by hand.",
        "class MosEisley < Formula",
        '  desc "Persistent multi-provider coding and review conversation"',
        '  homepage "https://github.com/joshuamyers22/mos-eisley"',
        f'  version "{release.version}"',
        '  skip_clean "libexec"',
        "  preserve_rpath",
    ]
    for system, brew_system in (("macos", "macos"), ("linux", "linux")):
        supported = [
            item for item in release.artifacts if item.platform.startswith(system)
        ]
        if not supported:
            continue
        formula.append(f"  on_{brew_system} do")
        for artifact in supported:
            cpu = "arm" if artifact.platform.endswith("aarch64") else "intel"
            formula.extend(
                [
                    f"    on_{cpu} do",
                    f'      url "{artifact.url}"',
                    f'      sha256 "{artifact.sha256}"',
                    "    end",
                ]
            )
        formula.append("  end")
    formula.extend(
        [
            "  def install",
            '    libexec.install Dir["*"]',
            '    (libexec/"installation-origin.json").write \'{"origin":"homebrew"}\'',
            '    bin.install_symlink libexec/"mos"',
            "  end",
            "  test do",
            '    assert_match version.to_s, shell_output("#{bin}/mos --version")',
            '    assert_match "credentials_required_to_install", '
            'shell_output("#{bin}/mos setup --json")',
            "  end",
            "end",
        ]
    )
    (output / "mos-eisley.rb").write_text("\n".join(formula) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
