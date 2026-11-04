"""Synthetic release artifacts with independent archive framing; no executables run."""

from __future__ import annotations

import hashlib
import io
import json
import struct
import tarfile
import zipfile
import zlib
from pathlib import Path

COMMIT = "a" * 40
TARGETS = ("linux-aarch64", "linux-x86_64", "macos-aarch64", "macos-x86_64")
EXPORT = """cryptography==50.0.2 \\
    --hash=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
cffi==2.1.1 ; platform_python_implementation != 'PyPy' \\
    --hash=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
pycparser==3.12 ; implementation_name != 'PyPy' \\
    --hash=sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
pywin32==312 ; sys_platform == 'win32' \\
    --hash=sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd
"""


def metadata(name: str, version: str, requires: tuple[str, ...] = ()) -> bytes:
    return (
        "Metadata-Version: 2.4\nName: "
        + name
        + "\nVersion: "
        + version
        + "\nLicense-Expression: MIT\nLicense-File: LICENSE\n"
        + "".join("Requires-Dist: " + r + "\n" for r in requires)
        + "\n"
    ).encode()


def carchive(files: dict[str, bytes], *, python: int = 312) -> bytes:
    # A structurally valid PKG inside an inert ELF-marked fixture, not executable.
    data = bytearray()
    toc = bytearray()
    for name, value in sorted(files.items()):
        encoded = name.encode() + b"\0"
        length = ((18 + len(encoded) + 15) // 16) * 16
        packed = zlib.compress(value)
        toc += struct.pack(
            "!IIIIBc", length, len(data), len(packed), len(value), 1, b"x"
        )
        toc += encoded + b"\0" * (length - 18 - len(encoded))
        data += packed
    cookie = struct.pack(
        "!8sIIII64s",
        b"MEI\x0c\x0b\x0a\x0b\x0e",
        len(data) + len(toc) + 88,
        len(data),
        len(toc),
        python,
        b"libpython3.12.so.1.0",
    )
    return b"\x7fELFsynthetic" + data + toc + cookie


def tar(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as stream:
        for name, value in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size = len(value)
            entry.mode = 0o600
            stream.addfile(entry, io.BytesIO(value))


def publication(root: Path, version: str = "0.2.0-rc.1", commit: str = COMMIT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    normalized = version.replace("-rc.", "rc")
    project = metadata("mos-eisley", normalized, ("cryptography>=50",))
    wheel_meta = f"mos_eisley-{normalized}.dist-info"
    with zipfile.ZipFile(
        root / f"mos_eisley-{normalized}-py3-none-any.whl", "w"
    ) as wheel:
        wheel.writestr(wheel_meta + "/METADATA", project)
        wheel.writestr(wheel_meta + "/licenses/LICENSE", "synthetic MIT notice")
    tar(
        root / f"mos_eisley-{normalized}.tar.gz",
        {
            f"mos_eisley-{normalized}/PKG-INFO": project,
            f"mos_eisley-{normalized}/LICENSE": b"synthetic MIT notice",
        },
    )
    (root / "SOURCE_COMMIT").write_text(commit + "\n")
    (root / "SHA256SUMS").write_text("synthetic checksums\n")
    (root / "requirements.runtime.txt").write_text(EXPORT)
    (root / "standalone").mkdir()
    (root / "managers").mkdir()
    (root / "managers/mos-eisley-preview.rb").write_text("synthetic formula\n")
    for name in ("release.json", "install.sh", "BOOTSTRAP_SHA256SUMS"):
        (root / "standalone" / name).write_text("synthetic " + name)
    for target in TARGETS:
        files = {
            "mos": b"\x7fELFinert synthetic application",
            "_internal/libpython3.12.so.1.0": b"\x7fELFinert Python library",
            "_internal/python-runtime-LICENSE.txt": b"synthetic Python license",
        }
        for name, ver, requires in (
            ("mos-eisley", normalized, ("cryptography>=50",)),
            (
                "cryptography",
                "50.0.2",
                ("cffi>=2; platform_python_implementation != 'PyPy'",),
            ),
            ("cffi", "2.1.1", ("pycparser",)),
            ("pycparser", "3.12", ()),
        ):
            directory = f"_internal/{name}-{ver}.dist-info"
            files[directory + "/METADATA"] = metadata(name, ver, requires)
            files[directory + "/licenses/LICENSE"] = b"synthetic MIT notice"
        for kind in ("application", "bootstrap"):
            facts = {
                "schema": 1,
                "kind": kind,
                "source_commit": commit,
                "platform": target,
                "version": version,
                "python_implementation": "CPython",
                "python_version": "3.12.14",
                "requirements_sha256": hashlib.sha256(EXPORT.encode()).hexdigest(),
                "python_license_sha256": hashlib.sha256(
                    files["_internal/python-runtime-LICENSE.txt"]
                ).hexdigest(),
            }
            files["_internal/mos-runtime.json"] = json.dumps(facts).encode()
            if kind == "application":
                tar(root / f"standalone/mos-{version}-{target}.tar.gz", files)
            else:
                embedded = {
                    n.removeprefix("_internal/"): b
                    for n, b in files.items()
                    if n != "mos"
                }
                (root / f"standalone/mos-install-{target}").write_bytes(
                    carchive(embedded)
                )
        q = root / "qualification" / target
        q.mkdir(parents=True)
        (q / f"qualification-{target}.json").write_text('{"synthetic":true}')
