"""Install the frozen archive through real Homebrew in an isolated local prefix."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from mos_eisley.app_release import platform_id


def main() -> int:
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    brew = shutil.which("brew")
    if brew is None:
        raise ValueError("actual Homebrew is required for this platform qualification")
    repository = Path(
        subprocess.check_output([brew, "--repository"], text=True).strip()
    )
    portable = sorted(
        (repository / "Library/Homebrew/vendor/portable-ruby").glob("*/bin/ruby")
    )
    archive = Path(f"dist/standalone/mos-{version}-{platform_id()}.tar.gz").resolve()
    work = Path(".work").resolve()
    work.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mos-brew-install-", dir=work) as temporary:
        base = Path(temporary).resolve()
        prefix = base / "prefix"
        clone = prefix / "Homebrew"
        subprocess.run(
            ["git", "clone", "--shared", str(repository), str(clone)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        environment = {
            **os.environ,
            "HOMEBREW_NO_AUTO_UPDATE": "1",
            "HOMEBREW_NO_ANALYTICS": "1",
            "HOMEBREW_NO_INSTALL_CLEANUP": "1",
            "HOMEBREW_NO_AUTOREMOVE": "1",
            "HOMEBREW_DEVELOPER": "1",
            "HOMEBREW_CACHE": str(base / "cache"),
            "HOMEBREW_LOGS": str(base / "logs"),
        }
        if portable:
            environment["HOMEBREW_RUBY_PATH"] = str(portable[-1])
        tap = clone / "Library/Taps/qualification/homebrew-mos-eisley"
        formula = tap / "Formula/mos-eisley.rb"
        formula.parent.mkdir(parents=True)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        formula.write_text(
            "class MosEisley < Formula\n"
            '  desc "Local frozen-runtime distribution qualification"\n'
            '  homepage "https://github.com/joshuamyers22/mos-eisley"\n'
            f'  url "{archive.as_uri()}"\n'
            f'  sha256 "{digest}"\n'
            f'  version "{version}"\n'
            '  skip_clean "libexec"\n'
            "  preserve_rpath\n"
            "  def install\n"
            '    libexec.install Dir["*"]\n'
            '    (libexec/"installation-origin.json").write \'{"origin":"homebrew"}\'\n'
            '    bin.install_symlink libexec/"mos"\n'
            "  end\n"
            "  test do\n"
            f'    assert_match "{version}", shell_output("#{{bin}}/mos --version")\n'
            "  end\n"
            "end\n"
        )
        subprocess.run(["git", "init", str(tap)], check=True, stdout=subprocess.DEVNULL)
        command = str(clone / "bin/brew")
        installed_prefix = Path(
            subprocess.check_output(
                [command, "--prefix"], env=environment, text=True
            ).strip()
        )
        selected = "qualification/mos-eisley/mos-eisley"
        subprocess.run([command, "install", selected], env=environment, check=True)
        subprocess.run(
            [str(installed_prefix / "bin/mos"), "--version"],
            env=environment,
            check=True,
        )
        subprocess.run(
            [str(installed_prefix / "bin/mos"), "setup", "--json"],
            env=environment,
            check=True,
        )
        subprocess.run([command, "test", selected], env=environment, check=True)
        subprocess.run([command, "uninstall", selected], env=environment, check=True)
        if (installed_prefix / "bin/mos").exists():
            raise ValueError("Homebrew left an active launcher after uninstall")
    print(
        json.dumps(
            {
                "platform": platform_id(),
                "homebrew_install_launch_test_uninstall": "passed_local_archive",
                "public_tap": "not_published",
                "paid_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
