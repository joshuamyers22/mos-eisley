"""Strict release-metadata projection, never a dependency resolver.

uv remains the resolver/hash verifier. This reader supports the marker vocabulary
used by the frozen CPython macOS/Linux export and metadata, rejecting new/unknown
forms instead of guessing. Requirement version constraints are preserved; selected
versions must equal the resolver's pins.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path

PYTHON_VERSION = "3.12.14"
PLATFORMS = ("linux-aarch64", "linux-x86_64", "macos-aarch64", "macos-x86_64")
_NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}"
_VERSION = r"[A-Za-z0-9][A-Za-z0-9.!+_-]{0,127}"
VERSION_MARKERS = {"python_version", "python_full_version", "implementation_version"}


def normalize(name: str) -> str:
    if re.fullmatch(_NAME, name) is None:
        raise ValueError("invalid distribution name")
    return re.sub(r"[-_.]+", "-", name).lower()


def project_version(version: str) -> str:
    if re.fullmatch(r"\d+\.\d+\.\d+(?:-rc\.\d+)?", version) is None:
        raise ValueError("unsupported application release version")
    return version.replace("-rc.", "rc")


@dataclass(frozen=True)
class Requirement:
    name: str
    extras: tuple[str, ...]
    marker: str
    declaration: str


def requirement(value: str) -> Requirement:
    if len(value) > 8192 or any(ord(c) < 32 for c in value):
        raise ValueError("invalid dependency declaration")
    head, sep, marker = value.partition(";")
    match = re.fullmatch(rf"\s*({_NAME})(?:\[([A-Za-z0-9_.,-]+)\])?(.*)", head)
    if match is None:
        raise ValueError("invalid dependency declaration")
    spec = match[3].strip()
    if spec and (
        spec[0] not in "(<>=!~"
        or re.fullmatch(r"[A-Za-z0-9.*+!<>=,~() _-]+", spec) is None
    ):
        raise ValueError("unsupported dependency source or specifier")
    if sep and not marker.strip():
        raise ValueError("empty dependency marker")
    extras = tuple(sorted({normalize(x) for x in (match[2] or "").split(",") if x}))
    return Requirement(normalize(match[1]), extras, marker.strip(), value)


def environment(platform: str, extra: str = "") -> dict[str, str]:
    if platform not in PLATFORMS:
        raise ValueError("unsupported SBOM platform")
    mac = platform.startswith("macos-")
    return {
        "sys_platform": "darwin" if mac else "linux",
        "os_name": "posix",
        "platform_system": "Darwin" if mac else "Linux",
        "platform_machine": "arm64" if mac else "aarch64",
        "platform_python_implementation": "CPython",
        "implementation_name": "cpython",
        "python_version": "3.12",
        "python_full_version": PYTHON_VERSION,
        "implementation_version": PYTHON_VERSION,
        "extra": extra,
    } | ({"platform_machine": "x86_64"} if platform.endswith("x86_64") else {})


def marker_applies(marker: str, values: dict[str, str]) -> bool:
    if not marker:
        return True
    if len(marker) > 8192:
        raise ValueError("dependency marker exceeds bound")
    try:
        tree = ast.parse(marker, mode="eval")
    except (SyntaxError, RecursionError) as error:
        raise ValueError("unsupported dependency marker") from error
    if len(list(ast.walk(tree))) > 256:
        raise ValueError("dependency marker exceeds bound")

    def visit(node: ast.AST, depth: int = 0) -> str | bool:
        if depth > 20:
            raise ValueError("dependency marker nesting exceeds bound")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And | ast.Or):
            results = [visit(x, depth + 1) for x in node.values]
            if not all(type(x) is bool for x in results):
                raise ValueError("invalid boolean dependency marker")
            return all(results) if isinstance(node.op, ast.And) else any(results)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left = visit(node.left, depth + 1)
            right_node = node.comparators[0]
            right = visit(right_node, depth + 1)
            if not isinstance(left, str) or not isinstance(right, str):
                raise ValueError("invalid dependency marker operands")
            op = node.ops[0]
            version = any(
                isinstance(x, ast.Name) and x.id in VERSION_MARKERS
                for x in (node.left, right_node)
            )
            if version and not isinstance(op, ast.In | ast.NotIn):
                if any(
                    re.fullmatch(r"\d+(?:\.\d+)*", v) is None for v in (left, right)
                ):
                    raise ValueError("unsupported version marker")
                a = tuple(int(x) for x in left.split("."))
                b = tuple(int(x) for x in right.split("."))
                width = max(len(a), len(b))
                a += (0,) * (width - len(a))
                b += (0,) * (width - len(b))
                if isinstance(op, ast.Eq):
                    return a == b
                if isinstance(op, ast.NotEq):
                    return a != b
                if isinstance(op, ast.Lt):
                    return a < b
                if isinstance(op, ast.LtE):
                    return a <= b
                if isinstance(op, ast.Gt):
                    return a > b
                if isinstance(op, ast.GtE):
                    return a >= b
            else:
                if any(
                    isinstance(x, ast.Name) and x.id == "extra"
                    for x in (node.left, right_node)
                ):
                    left = normalize(left) if left else ""
                    right = normalize(right) if right else ""
                if isinstance(op, ast.Eq):
                    return left == right
                if isinstance(op, ast.NotEq):
                    return left != right
                if isinstance(op, ast.In):
                    return left in right
                if isinstance(op, ast.NotIn):
                    return left not in right
        raise ValueError("unsupported dependency marker vocabulary")

    result = visit(tree.body)
    if type(result) is not bool:
        raise ValueError("invalid dependency marker result")
    return result


@dataclass(frozen=True)
class Distribution:
    name: str
    version: str
    requirements: tuple[Requirement, ...]
    license_expression: str | None
    license_name: str | None
    license_files: tuple[str, ...]


def distribution(raw: bytes) -> Distribution:
    if len(raw) > 512 * 1024:
        raise ValueError("distribution metadata exceeds bound")
    message = BytesParser(policy=compat32).parsebytes(raw)
    for field in ("Name", "Version", "Metadata-Version"):
        if len(message.get_all(field, [])) != 1:
            raise ValueError("missing or duplicate distribution identity")
    name = normalize(str(message["Name"]))
    version = str(message["Version"])
    if re.fullmatch(_VERSION, version) is None:
        raise ValueError("invalid distribution version")
    declared = tuple(str(v) for v in message.get_all("Requires-Dist", []))
    licenses = tuple(str(v) for v in message.get_all("License-File", []))
    if len(declared) > 256 or len(licenses) > 64:
        raise ValueError("distribution metadata list exceeds bound")

    def license_value(field: str) -> str | None:
        values = message.get_all(field, [])
        if len(values) > 1:
            raise ValueError("duplicate license declaration")
        if not values:
            return None
        value = str(values[0])
        if len(value) > 256 or any(ord(c) < 32 for c in value) or value == "UNKNOWN":
            return None
        return value

    return Distribution(
        name,
        version,
        tuple(requirement(v) for v in declared),
        license_value("License-Expression"),
        license_value("License"),
        licenses,
    )


def runtime_export(path: Path, platform: str) -> dict[str, str]:
    if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("unsafe runtime dependency export")
    result: dict[str, str] = {}
    pending: tuple[str, str, str] | None = None
    hashes = 0

    def finish() -> None:
        if pending is None:
            return
        if not hashes:
            raise ValueError("runtime export is not hash-pinned")
        name, version, marker = pending
        if marker_applies(marker, environment(platform)):
            if name in result:
                raise ValueError("ambiguous runtime export pins")
            result[name] = version

    for raw in path.read_text().splitlines():
        line = raw.strip().removesuffix("\\").strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--hash="):
            if (
                pending is None
                or re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", line) is None
            ):
                raise ValueError("invalid runtime export hash")
            hashes += 1
            continue
        finish()
        match = re.fullmatch(rf"({_NAME})==({_VERSION})(?:\s*;\s*(.+))?", line)
        if match is None:
            raise ValueError("unsupported runtime export line")
        pending = (normalize(match[1]), match[2], match[3] or "")
        hashes = 0
    finish()
    if not result or len(result) > 1000:
        raise ValueError("empty or excessive runtime dependency export")
    return result
