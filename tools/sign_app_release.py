"""Sign application metadata with an owner-provisioned Ed25519 key file."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import stat
import tomllib
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.app_release import RELEASE_ORIGIN, canonical, parse_release
from mos_eisley.app_release_key import PUBLISHER_PUBLIC_KEY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--notes", required=True)
    parser.add_argument("--channel", choices=("stable", "preview"), default="stable")
    args = parser.parse_args()
    info = args.key_file.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_size != 32
    ):
        raise ValueError(
            "signing key must be an owned 0600 32-byte raw Ed25519 key file"
        )
    key = Ed25519PrivateKey.from_private_bytes(args.key_file.read_bytes())
    if key.public_key().public_bytes_raw().hex() != PUBLISHER_PUBLIC_KEY:
        raise ValueError("signing key does not match the enrolled publisher")
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    inventory: list[dict[str, object]] = []
    for archive in sorted(args.artifacts.glob(f"mos-{version}-*.tar.gz")):
        target = archive.name.removeprefix(f"mos-{version}-").removesuffix(".tar.gz")
        inventory.append(
            {
                "platform": target,
                "url": f"{RELEASE_ORIGIN}v{version}/{archive.name}",
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "size": archive.stat().st_size,
            }
        )
    payload = {
        "schema": 1,
        "version": version,
        "channel": args.channel,
        "source_commit": args.commit,
        "notes": args.notes,
        "artifacts": inventory,
        "storage_epoch": 1,
        "withdrawn": False,
    }
    raw = canonical(
        {
            "payload": payload,
            "signature": base64.b64encode(key.sign(canonical(payload))).decode(),
        }
    )
    parse_release(raw)
    (args.artifacts / "release.json").write_bytes(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
