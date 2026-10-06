"""Owner-invoked Ed25519 enrollment; private key bytes are never printed."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument(
        "--create",
        action="store_true",
        help="create a new private key without overwriting any existing file",
    )
    args = parser.parse_args()
    path = args.key_file.expanduser().absolute()
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = parent.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("signing key directory must be owned and private (0700)")
    if args.create:
        key = Ed25519PrivateKey.generate()
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(key.private_bytes_raw())
            stream.flush()
            os.fsync(stream.fileno())
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_size != 32
    ):
        raise ValueError("signing key must be an owned 0600 raw Ed25519 key")
    key = Ed25519PrivateKey.from_private_bytes(path.read_bytes())
    public = key.public_key().public_bytes_raw().hex()
    Path("src/mos_eisley/app_release_key.py").write_text(
        '"""Owner-enrolled publisher trust root; private key stays external."""\n\n'
        f'PUBLISHER_PUBLIC_KEY = (\n    "{public}"\n)\n'
    )
    print(
        "Publisher public key enrolled in source. "
        "Private key remains at the selected external path. "
        "Accountable review and CI secret configuration "
        "are required before publication."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
