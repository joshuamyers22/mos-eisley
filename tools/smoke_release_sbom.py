"""Check real four-platform software with explicitly unsigned auxiliary fixtures.

This unprivileged CI assembly cannot be installed or published as a signed
release. The protected workflow later inventories its actual signed metadata
and manager files. Only those auxiliary files are fixtures here; all eight native
payloads, wheel, source distribution and dependency export are the actual builds.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from tools.release_sbom import build_sbom, validate_sbom


def main() -> int:
    root = Path("dist")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    for path in (root / "standalone/release.json", root / "managers"):
        if path.exists() or path.is_symlink():
            raise ValueError(
                "SBOM fixture assembly refuses prepared publication inputs"
            )
    (root / "managers").mkdir()
    (root / "managers/mos-eisley-preview.rb").write_text(
        "# UNSIGNED AUXILIARY FIXTURE: SBOM CI only; cannot install or publish.\n"
    )
    (root / "standalone/release.json").write_text(
        '{"fixture":"unsigned SBOM CI auxiliary metadata; not a release"}\n'
    )
    shutil.copyfile("distribution/install.sh", root / "standalone/install.sh")
    shutil.copyfile("requirements.runtime.txt", root / "requirements.runtime.txt")
    (root / "SOURCE_COMMIT").write_text(commit + "\n")
    bom = build_sbom(root, commit)
    (root / "release-sbom.cdx.json").write_text(json.dumps(bom, sort_keys=True))
    validate_sbom(root, commit)
    print("SBOM CI: all four real native targets covered; auxiliary fixtures unsigned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
