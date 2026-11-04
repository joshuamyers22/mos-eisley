"""Bounded, non-executing readers for release software inventory.

The independent CArchive reader follows the pinned PyInstaller 6.22.3 cookie/TOC
format, not its unbounded decompressor. Embedded PYZ/marshal content is hashed,
never deserialized or executed. No archive is extracted onto the host.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import stat
import struct
import tarfile
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, BinaryIO

MAX_ARTIFACT = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_FILES = 20_000
MAX_MEMBER = 128 * 1024 * 1024
MAX_RETAINED = 16 * 1024 * 1024
MAX_METADATA = 512 * 1024
MAX_TOC = 8 * 1024 * 1024
MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
COOKIE = struct.Struct("!8sIIII64s")
ENTRY = struct.Struct("!IIIIBc")


@dataclass(frozen=True)
class FileRecord:
    name: str
    size: int
    sha256: str
    header: bytes
    data: bytes | None = None


@dataclass(frozen=True)
class Archive:
    files: tuple[FileRecord, ...]
    python_tag: int | None = None
    python_library: str | None = None


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or not path.parts
        or len(name.encode()) > 4096
        or str(path) != name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
    ):
        raise ValueError("unsafe SBOM archive path")
    return name


def regular(path: Path, limit: int = MAX_ARTIFACT) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("unsafe or oversized SBOM input")


def file_digest(path: Path) -> str:
    regular(path)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _retain(name: str) -> bool:
    return PurePosixPath(name).name in {"METADATA", "PKG-INFO", "mos-runtime.json"}


def _record(name: str, size: int, stream: IO[bytes]) -> FileRecord:
    if size < 0 or size > MAX_MEMBER or (_retain(name) and size > MAX_METADATA):
        raise ValueError("SBOM member exceeds size bound")
    checksum = hashlib.sha256()
    data = bytearray()
    header = b""
    count = 0
    while block := stream.read(min(256 * 1024, size - count + 1)):
        count += len(block)
        if count > size:
            raise ValueError("SBOM member size mismatch")
        if not header:
            header = block[:4]
        checksum.update(block)
        if _retain(name):
            data.extend(block)
    if count != size:
        raise ValueError("truncated SBOM member")
    return FileRecord(
        name, size, checksum.hexdigest(), header, bytes(data) if _retain(name) else None
    )


class _TarInput(io.RawIOBase):
    """Bound decompression and tar's hidden PAX/GNU header reads before allocation."""

    def __init__(self, stream: gzip.GzipFile) -> None:
        self.stream = stream
        self.position = 0

    def tell(self) -> int:
        return self.position

    def read(self, size: int = -1) -> bytes:
        if size < 0 or size > MAX_METADATA:
            raise ValueError("tar read size bound exceeded")
        if self.position + size > MAX_EXPANDED + MAX_FILES * 1024:
            raise ValueError("tar decompression bound exceeded")
        data = self.stream.read(size)
        self.position += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        target = offset if whence == 0 else self.position + offset
        if whence not in (0, 1) or target < self.position:
            raise ValueError("non-forward tar inventory seek")
        while self.position < target:
            if not self.read(min(256 * 1024, target - self.position)):
                raise ValueError("truncated tar inventory")
        return self.position


def tar_inventory(path: Path) -> Archive:
    regular(path)
    files: list[FileRecord] = []
    names: set[str] = set()
    expanded = 0
    retained = 0
    with (
        gzip.open(path, "rb") as compressed,
        tarfile.open(
            fileobj=_TarInput(compressed),
            mode="r:",
        ) as archive,
    ):
        for member in archive:
            name = safe_name(member.name.rstrip("/") if member.isdir() else member.name)
            if name in names or len(names) >= MAX_FILES:
                raise ValueError("duplicate or excessive SBOM archive members")
            names.add(name)
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("SBOM archive links and special files are forbidden")
            expanded += member.size
            if expanded > MAX_EXPANDED:
                raise ValueError("SBOM archive expansion bound exceeded")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("missing SBOM archive member")
            with stream:
                record = _record(name, member.size, stream)
                retained += len(record.data or b"")
                if retained > MAX_RETAINED:
                    raise ValueError("retained metadata exceeds bound")
                files.append(record)
    return Archive(tuple(sorted(files, key=lambda f: f.name)))


def wheel_inventory(path: Path) -> Archive:
    regular(path)
    files: list[FileRecord] = []
    names: set[str] = set()
    expanded = 0
    retained = 0
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            name = safe_name(member.filename.rstrip("/"))
            if name in names or len(names) >= MAX_FILES:
                raise ValueError("duplicate or excessive wheel members")
            names.add(name)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or member.flag_bits & 1:
                raise ValueError("wheel links and encrypted members are forbidden")
            if member.is_dir():
                continue
            expanded += member.file_size
            if expanded > MAX_EXPANDED:
                raise ValueError("wheel expansion bound exceeded")
            with archive.open(member) as stream:
                record = _record(name, member.file_size, stream)
                retained += len(record.data or b"")
                if retained > MAX_RETAINED:
                    raise ValueError("retained metadata exceeds bound")
                files.append(record)
    return Archive(tuple(sorted(files, key=lambda f: f.name)))


def _cookie(stream: BinaryIO, size: int) -> tuple[int, int, int, int, int, str]:
    end = size
    while end >= len(MAGIC):
        start = max(0, end - 8192)
        stream.seek(start)
        block = stream.read(end - start)
        found = block.rfind(MAGIC)
        if found >= 0:
            offset = start + found
            stream.seek(offset)
            raw = stream.read(COOKIE.size)
            if len(raw) != COOKIE.size:
                raise ValueError("truncated CArchive cookie")
            _, length, toc_at, toc_size, python, library = COOKIE.unpack(raw)
            base = offset + COOKIE.size - length
            if (
                base < 0
                or toc_size > MAX_TOC
                or toc_at + toc_size != length - COOKIE.size
                or offset + COOKIE.size > size
            ):
                raise ValueError("invalid CArchive cookie bounds")
            lib = library.split(b"\0", 1)[0].decode("ascii")
            safe_name(lib)
            return base, toc_at, toc_size, python, offset, lib
        end = start + len(MAGIC) - 1
    raise ValueError("missing CArchive cookie")


def carchive_inventory(path: Path) -> Archive:
    regular(path)
    files: list[FileRecord] = []
    names: set[str] = set()
    expanded = 0
    retained = 0
    spans: list[tuple[int, int]] = []
    with path.open("rb") as stream:
        base, toc_at, toc_size, python, _, library = _cookie(
            stream, path.stat().st_size
        )
        stream.seek(base + toc_at)
        toc = stream.read(toc_size)
        offset = 0
        entries = 0
        while offset < len(toc):
            if offset + ENTRY.size > len(toc):
                raise ValueError("truncated CArchive TOC")
            length, at, size, unpacked, compressed, kind = ENTRY.unpack_from(
                toc, offset
            )
            if length <= ENTRY.size or offset + length > len(toc):
                raise ValueError("invalid CArchive TOC entry")
            raw_name = toc[offset + ENTRY.size : offset + length]
            offset += length
            entries += 1
            if entries > MAX_FILES or b"\0" not in raw_name:
                raise ValueError("excessive or invalid CArchive entries")
            first, padding = raw_name.split(b"\0", 1)
            if padding.strip(b"\0"):
                raise ValueError("invalid CArchive name padding")
            name = first.decode("utf-8")
            if kind == b"o":
                if size or unpacked or compressed or len(name) > 1024:
                    raise ValueError("invalid CArchive runtime option")
                continue
            safe_name(name)
            if (
                name in names
                or kind not in (b"b", b"x", b"z", b"Z", b"m", b"M", b"s")
                or compressed not in (0, 1)
                or at + size > toc_at
                or unpacked > MAX_MEMBER
                or size > MAX_MEMBER
            ):
                raise ValueError("unsafe or duplicate CArchive payload")
            names.add(name)
            expanded += unpacked
            if expanded > MAX_EXPANDED or (_retain(name) and unpacked > MAX_METADATA):
                raise ValueError("CArchive expansion bound exceeded")
            if size:
                spans.append((at, at + size))
            stream.seek(base + at)
            # Compressed input is bounded by the admitted executable size. The
            # explicit output cap also rejects malicious advertised lengths.
            raw = stream.read(size)
            if len(raw) != size:
                raise ValueError("truncated CArchive payload")
            if compressed:
                decoder = zlib.decompressobj()
                payload = decoder.decompress(raw, unpacked + 1)
                if (
                    len(payload) != unpacked
                    or not decoder.eof
                    or decoder.unused_data
                    or decoder.unconsumed_tail
                ):
                    raise ValueError("invalid compressed CArchive payload")
            else:
                payload = raw
                if len(payload) != unpacked:
                    raise ValueError("invalid CArchive payload length")
            record = _record("_internal/" + name, unpacked, io.BytesIO(payload))
            retained += len(record.data or b"")
            if retained > MAX_RETAINED:
                raise ValueError("retained metadata exceeds bound")
            files.append(record)
        ordered = sorted(spans)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:], strict=False)):
            raise ValueError("overlapping CArchive payloads")
    return Archive(tuple(sorted(files, key=lambda f: f.name)), python, library)


def native_format(header: bytes) -> str | None:
    if header == b"\x7fELF":
        return "ELF"
    if header in (
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
    ):
        return "Mach-O"
    return None
