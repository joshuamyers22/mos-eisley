"""Signed, inert application release metadata; no import-time I/O."""

from __future__ import annotations

import base64
import hashlib
import json
import platform
import re
import time
from dataclasses import dataclass
from importlib.metadata import version as distribution_version
from typing import Literal, cast
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from mos_eisley.app_release_key import PUBLISHER_PUBLIC_KEY

REPOSITORY = "joshuamyers22/mos-eisley"
RELEASE_ORIGIN = f"https://github.com/{REPOSITORY}/releases/download/"
FEEDS = {
    "stable": f"https://github.com/{REPOSITORY}/releases/latest/download/release.json",
    "preview": f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=10",
}
MAX_METADATA = 128 * 1024
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
STORAGE_EPOCH = 1
VersionTuple = tuple[int, int, int, int, int]
Channel = Literal["stable", "preview"]


class ReleaseError(ValueError):
    """Release or installation cannot be safely admitted."""


def version_key(value: str) -> VersionTuple:
    match = re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-rc\.(0|[1-9]\d*))?", value
    )
    if match is None or len(value) > 50:
        raise ReleaseError("unsupported semantic version")
    return (
        int(match[1]),
        int(match[2]),
        int(match[3]),
        int(match[4] is None),
        int(match[4] or 0),
    )


def platform_id() -> str:
    system = {"Darwin": "macos", "Linux": "linux"}.get(platform.system())
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(platform.machine().lower())
    if system is None or arch is None:
        raise ReleaseError("unsupported platform; native Windows is not supported")
    return f"{system}-{arch}"


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


@dataclass(frozen=True)
class Artifact:
    platform: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class Release:
    version: str
    channel: Channel
    source_commit: str
    notes: str
    artifacts: tuple[Artifact, ...]
    storage_epoch: int
    raw: bytes

    def artifact(self, target: str) -> Artifact:
        for item in self.artifacts:
            if item.platform == target:
                return item
        raise ReleaseError(f"release has no artifact for {target}")


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReleaseError("invalid release object")
    if any(not isinstance(key, str) for key in cast(dict[object, object], value)):
        raise ReleaseError("invalid release object")
    return cast(dict[str, object], value)


def _text(value: object, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > limit
        or any(ord(c) < 32 for c in value)
    ):
        raise ReleaseError("invalid release text")
    return value


def parse_release(raw: bytes, *, public_key: str | None = None) -> Release:
    if len(raw) > MAX_METADATA:
        raise ReleaseError("release metadata too large")
    try:
        envelope = _mapping(json.loads(raw))
        if set(envelope) != {"payload", "signature"}:
            raise ReleaseError("unexpected release envelope fields")
        payload = _mapping(envelope["payload"])
        key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(public_key or PUBLISHER_PUBLIC_KEY)
        )
        key.verify(
            base64.b64decode(_text(envelope["signature"], 100), validate=True),
            canonical(payload),
        )
    except (ValueError, TypeError, KeyError, InvalidSignature) as error:
        raise ReleaseError("release publisher signature is invalid") from error
    if set(payload) != {
        "schema",
        "version",
        "channel",
        "source_commit",
        "notes",
        "artifacts",
        "storage_epoch",
        "withdrawn",
    }:
        raise ReleaseError("unexpected release payload fields")
    if (
        type(payload["schema"]) is not int
        or payload["schema"] != 1
        or payload["withdrawn"] is not False
        or type(payload["storage_epoch"]) is not int
        or payload["storage_epoch"] != STORAGE_EPOCH
    ):
        raise ReleaseError("withdrawn or incompatible release")
    version = _text(payload["version"], 50)
    version_key(version)
    channel = payload["channel"]
    if channel not in ("stable", "preview") or (channel == "stable" and "-" in version):
        raise ReleaseError("invalid release channel")
    commit = _text(payload["source_commit"], 40)
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ReleaseError("invalid source commit")
    notes = _text(payload["notes"], 2000)
    values = payload["artifacts"]
    if not isinstance(values, list) or not 1 <= len(cast(list[object], values)) <= 4:
        raise ReleaseError("invalid artifact inventory")
    artifacts: list[Artifact] = []
    for value in cast(list[object], values):
        item = _mapping(value)
        if set(item) != {"platform", "url", "sha256", "size"}:
            raise ReleaseError("unexpected artifact fields")
        target = _text(item["platform"], 30)
        if target not in {
            "macos-aarch64",
            "macos-x86_64",
            "linux-aarch64",
            "linux-x86_64",
        } or target in {a.platform for a in artifacts}:
            raise ReleaseError("invalid or duplicate platform")
        url = _text(item["url"], 300)
        if url != f"{RELEASE_ORIGIN}v{version}/mos-{version}-{target}.tar.gz":
            raise ReleaseError("artifact URL is outside the exact release")
        digest = _text(item["sha256"], 64)
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ReleaseError("invalid artifact digest")
        size = item["size"]
        if type(size) is not int or not 1 <= size <= MAX_ARCHIVE:
            raise ReleaseError("invalid artifact size")
        artifacts.append(Artifact(target, url, digest, size))
    return Release(
        version,
        channel,
        commit,
        notes,
        tuple(artifacts),
        STORAGE_EPOCH,
        raw,
    )


class _Redirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Request:
        # GitHub sends immutable assets to its dedicated CDN. No other origins,
        # credentials, ports or protocols are accepted, including on later hops.
        parsed = urlsplit(newurl)
        if (
            parsed.scheme != "https"
            or not (
                parsed.hostname == "release-assets.githubusercontent.com"
                or (
                    parsed.hostname == "github.com"
                    and newurl.startswith(RELEASE_ORIGIN)
                    and parsed.path.endswith("/release.json")
                )
            )
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ReleaseError("unexpected release redirect")
        return Request(newurl, headers={"User-Agent": "mos-eisley-release/1"})


def download(url: str, limit: int) -> bytes:
    if not (url in FEEDS.values() or url.startswith(RELEASE_ORIGIN)):
        raise ReleaseError("untrusted distribution endpoint")
    request = Request(url, headers={"User-Agent": "mos-eisley-release/1"})
    with build_opener(_Redirects()).open(request, timeout=10) as response:
        started = time.monotonic()
        chunks: list[bytes] = []
        count = 0
        while count <= limit:
            if time.monotonic() - started > 60:
                raise ReleaseError("download exceeded deadline")
            chunk = response.read(min(1024 * 1024, limit + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            chunks.append(chunk)
        raw = b"".join(chunks)
    if len(raw) > limit:
        raise ReleaseError("download exceeds byte limit")
    return raw


def verify_archive(raw: bytes, artifact: Artifact) -> None:
    if len(raw) != artifact.size or hashlib.sha256(raw).hexdigest() != artifact.sha256:
        raise ReleaseError("archive integrity check failed")


def release_metadata(channel: Channel) -> bytes:
    if channel == "stable":
        return download(FEEDS["stable"], MAX_METADATA)
    value: object = json.loads(download(FEEDS["preview"], MAX_METADATA))
    if not isinstance(value, list) or len(cast(list[object], value)) > 10:
        raise ReleaseError("invalid preview release inventory")
    candidates: list[str] = []
    for item in cast(list[object], value):
        entry = _mapping(item)
        if entry.get("draft") is False and entry.get("prerelease") is True:
            tag = _text(entry.get("tag_name"), 51)
            if not tag.startswith("v") or "-rc." not in tag:
                continue
            version_key(tag[1:])
            candidates.append(tag[1:])
    if not candidates:
        raise ReleaseError("no published preview release")
    selected = max(candidates, key=version_key)
    return download(f"{RELEASE_ORIGIN}v{selected}/release.json", MAX_METADATA)


def application_version() -> str:
    value = distribution_version("mos-eisley")
    match = re.fullmatch(r"(\d+\.\d+\.\d+)rc(\d+)", value)
    canonical_version = f"{match[1]}-rc.{match[2]}" if match else value
    version_key(canonical_version)
    return canonical_version
