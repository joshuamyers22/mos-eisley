"""Deterministic CycloneDX inventory of the actual release software payloads.

Generation and stdlib-only publication admission use the same bounded artifact
projection. Admission recomputes it, rather than trusting a component count or a
builder's self-reported list. Native versions not established by metadata remain
file identities with hashes; this is not vulnerability or legal clearance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform as host_platform
import re
import shutil
import subprocess
import sys
import sysconfig
import uuid
from collections import deque
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import quote

from tools.sbom_archive import (
    FileRecord,
    carchive_inventory,
    file_digest,
    native_format,
    regular,
    safe_name,
    tar_inventory,
    wheel_inventory,
)
from tools.sbom_metadata import (
    PLATFORMS,
    PYTHON_VERSION,
    Distribution,
    distribution,
    environment,
    marker_applies,
    project_version,
    runtime_export,
)

FACTS = "_internal/mos-runtime.json"
PYTHON_LICENSE = "_internal/python-runtime-LICENSE.txt"
MAX_BOM = 32 * 1024 * 1024
Component = dict[str, object]


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("invalid SBOM object")
    values = cast(dict[object, object], value)
    if not all(isinstance(k, str) for k in values):
        raise ValueError("invalid SBOM object")
    return cast(dict[str, object], values)


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate SBOM JSON key")
        result[key] = value
    return result


def _json(raw: bytes) -> dict[str, object]:
    if len(raw) > MAX_BOM:
        raise ValueError("SBOM JSON exceeds bound")
    return _object(json.loads(raw, object_pairs_hook=_unique))


def _properties(**values: str) -> list[dict[str, str]]:
    return [
        {"name": "mos:" + k.replace("_", "-"), "value": v}
        for k, v in sorted(values.items())
    ]


def _licenses(meta: Distribution) -> list[dict[str, object]]:
    if meta.license_expression:
        return [{"expression": meta.license_expression}]
    if meta.license_name:
        return [{"license": {"name": meta.license_name}}]
    return []


def _one(root: Path, pattern: str) -> Path:
    files = sorted(root.glob(pattern))
    if len(files) != 1:
        raise ValueError("release requires one wheel and one source distribution")
    regular(files[0])
    return files[0]


def _metadata(
    files: tuple[FileRecord, ...], suffix: str
) -> tuple[FileRecord, Distribution]:
    matches = [f for f in files if f.name.endswith(suffix)]
    if len(matches) != 1 or matches[0].data is None:
        raise ValueError("missing or ambiguous application package metadata")
    return matches[0], distribution(matches[0].data)


def _graph(
    metadata: dict[str, tuple[FileRecord, Distribution]],
    pins: dict[str, str],
    target: str,
    roots: tuple[str, ...],
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    extras: dict[str, set[str]] = {name: {""} for name in roots}
    queue = deque(roots)
    visits = 0
    while queue:
        name = queue.popleft()
        visits += 1
        if visits > 10_000 or name not in metadata:
            raise ValueError("missing or excessive runtime dependency closure")
        _, meta = metadata[name]
        if name != "mos-eisley" and pins.get(name) != meta.version:
            raise ValueError("runtime distribution differs from frozen export: " + name)
        edges = graph.setdefault(name, set())
        for req in meta.requirements:
            if not any(
                marker_applies(req.marker, environment(target, e))
                for e in sorted(extras[name])
            ):
                continue
            if req.name not in pins or req.name not in metadata:
                raise ValueError("missing locked runtime dependency: " + req.name)
            edges.add(req.name)
            selected = {"", *req.extras}
            before = extras.get(req.name, set())
            after = before | selected
            if len(after) > 128:
                raise ValueError("runtime dependency extras exceed bound")
            if req.name not in graph or after != before:
                extras[req.name] = after
                if req.name not in queue:
                    queue.append(req.name)
    return graph


def build_sbom(
    root: Path, commit: str, expected_version: str | None = None
) -> Component:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("invalid SBOM source commit")
    requirements = root / "requirements.runtime.txt"
    regular(requirements, 4 * 1024 * 1024)
    export_sha = file_digest(requirements)
    wheel = _one(root, "*.whl")
    source = _one(root, "*.tar.gz")
    wheel_files = wheel_inventory(wheel).files
    wheel_record, project = _metadata(wheel_files, ".dist-info/METADATA")
    source_files = tar_inventory(source).files
    _, source_project = _metadata(source_files, "/PKG-INFO")
    if project.name != "mos-eisley" or source_project != project:
        raise ValueError("wheel/source distribution identity differs")

    root_ref = "application:mos-eisley"
    components: dict[str, Component] = {}
    dependencies: dict[str, set[str]] = {root_ref: set()}
    versions: set[str] = set()

    def add(component: Component, edges: set[str] | None = None) -> str:
        ref = str(component["bom-ref"])
        if ref in components or ref == root_ref:
            raise ValueError("duplicate SBOM component identity")
        components[ref] = component
        dependencies[ref] = edges if edges is not None else set()
        return ref

    def artifact(path: Path) -> str:
        regular(path)
        ref = "artifact:" + str(path.relative_to(root))
        add(
            {
                "type": "file",
                "bom-ref": ref,
                "name": path.name,
                "hashes": [{"alg": "SHA-256", "content": file_digest(path)}],
            }
        )
        dependencies[root_ref].add(ref)
        return ref

    def package_files(path: Path, files: tuple[FileRecord, ...]) -> None:
        ref = artifact(path)
        for file in files:
            inner = ref + "!" + file.name
            add(
                {
                    "type": "file",
                    "bom-ref": inner,
                    "name": file.name,
                    "hashes": [{"alg": "SHA-256", "content": file.sha256}],
                }
            )
            dependencies[ref].add(inner)
        record, meta = _metadata(
            files, ".dist-info/METADATA" if path == wheel else "/PKG-INFO"
        )
        names = {f.name for f in files}
        directory = str(PurePosixPath(record.name).parent)
        for declared in meta.license_files:
            safe_name(declared)
            if not any(
                p in names
                for p in (
                    directory + "/licenses/" + declared,
                    directory + "/" + declared,
                )
            ):
                raise ValueError("project license file is not packaged")

    package_files(wheel, wheel_files)
    package_files(source, source_files)
    for path in (
        requirements,
        root / "SOURCE_COMMIT",
        root / "standalone/release.json",
        root / "standalone/install.sh",
    ):
        artifact(path)
    if (root / "SOURCE_COMMIT").read_text().strip() != commit:
        raise ValueError("SBOM source record differs")
    managers = sorted((root / "managers").glob("*.rb"))
    if not managers:
        raise ValueError("missing software manager definition")
    for path in managers:
        artifact(path)

    archives = sorted((root / "standalone").glob("mos-*.tar.gz"))
    bootstraps = sorted((root / "standalone").glob("mos-install-*"))
    if len(archives) != 4 or {
        p.name.removeprefix("mos-install-") for p in bootstraps
    } != set(PLATFORMS):
        raise ValueError("incomplete release SBOM platform set")

    for target in PLATFORMS:
        pins = runtime_export(requirements, target)
        matches = [p for p in archives if p.name.endswith("-" + target + ".tar.gz")]
        if len(matches) != 1:
            raise ValueError("missing or duplicate native archive platform")
        for kind, path, archive in (
            ("application", matches[0], tar_inventory(matches[0])),
            (
                "bootstrap",
                root / "standalone" / ("mos-install-" + target),
                carchive_inventory(root / "standalone" / ("mos-install-" + target)),
            ),
        ):
            artifact_ref = artifact(path)
            files = {f.name: f for f in archive.files}
            fact_file = files.get(FACTS)
            if fact_file is None or fact_file.data is None:
                raise ValueError("missing native runtime inventory")
            facts = _json(fact_file.data)
            version = facts.get("version")
            if (
                set(facts)
                != {
                    "schema",
                    "kind",
                    "source_commit",
                    "platform",
                    "version",
                    "python_implementation",
                    "python_version",
                    "requirements_sha256",
                    "python_license_sha256",
                }
                or type(facts["schema"]) is not int
                or facts["schema"] != 1
                or facts["kind"] != kind
                or facts["source_commit"] != commit
                or facts["platform"] != target
                or not isinstance(version, str)
                or project_version(version) != project.version
                or facts["python_implementation"] != "CPython"
                or facts["python_version"] != PYTHON_VERSION
                or facts["requirements_sha256"] != export_sha
            ):
                raise ValueError("native runtime inventory identity differs")
            versions.add(version)
            if kind == "application" and path.name != f"mos-{version}-{target}.tar.gz":
                raise ValueError("native archive version differs")
            license_file = files.get(PYTHON_LICENSE)
            if (
                license_file is None
                or not license_file.size
                or facts["python_license_sha256"] != license_file.sha256
            ):
                raise ValueError("missing or altered CPython license evidence")
            if kind == "application":
                executable = files.get("mos")
                if executable is None or native_format(executable.header) is None:
                    raise ValueError("missing native application executable")
                # Read only the bounded PKG framing; never deserialize embedded Python.
                # The onedir executable itself is already hashed in the archive.
                python_libs = [
                    f
                    for f in files.values()
                    if ("libpython3.12" in f.name or f.name.endswith("/Python"))
                    and native_format(f.header)
                ]
            else:
                if (
                    archive.python_tag != 312
                    or not archive.python_library
                    or "python3.12" not in archive.python_library.lower()
                ):
                    raise ValueError("bootstrap interpreter cookie differs")
                python_libs = [
                    f
                    for f in files.values()
                    if f.name.endswith("/" + str(archive.python_library))
                    and native_format(f.header)
                ]
            if not python_libs:
                raise ValueError("missing bundled interpreter library")

            prefix = kind + ":" + target + ":"
            for file in archive.files:
                ref = prefix + "file:" + file.name
                props = _properties(platform=target, container=path.name)
                native = native_format(file.header)
                if native:
                    props += _properties(
                        native_format=native, native_version="not-established"
                    )
                add(
                    {
                        "type": "file",
                        "bom-ref": ref,
                        "name": file.name,
                        "hashes": [{"alg": "SHA-256", "content": file.sha256}],
                        "properties": props,
                    }
                )
                dependencies[artifact_ref].add(ref)

            python_ref = prefix + "python"
            add(
                {
                    "type": "application",
                    "bom-ref": python_ref,
                    "name": "CPython",
                    "version": PYTHON_VERSION,
                    "purl": "pkg:generic/cpython@" + PYTHON_VERSION,
                    "licenses": [
                        {"license": {"name": "CPython license (bundled LICENSE.txt)"}}
                    ],
                    "properties": _properties(
                        platform=target,
                        version_evidence="native-build-and-frozen-runtime-probe",
                    ),
                },
                {prefix + "file:" + f.name for f in python_libs}
                | {prefix + "file:" + PYTHON_LICENSE},
            )
            dependencies[artifact_ref].add(python_ref)

            primary: dict[str, tuple[FileRecord, Distribution]] = {}
            observed: list[tuple[FileRecord, Distribution]] = []
            for file in archive.files:
                if not file.name.endswith(".dist-info/METADATA"):
                    continue
                if file.data is None:
                    raise ValueError("missing distribution metadata bytes")
                meta = distribution(file.data)
                observed.append((file, meta))
                if len(PurePosixPath(file.name).parts) == 3:
                    if meta.name in primary:
                        raise ValueError("duplicate native distribution metadata")
                    primary[meta.name] = (file, meta)
            if "mos-eisley" not in primary or primary["mos-eisley"][1] != project:
                raise ValueError("native project metadata differs from wheel")
            graph = _graph(
                primary,
                pins,
                target,
                ("mos-eisley",) if kind == "application" else ("cryptography",),
            )
            if kind == "application" and set(graph) - {"mos-eisley"} != set(pins):
                raise ValueError("runtime export is not completely covered")
            package_refs = {
                name: prefix + "package:" + record.name
                for name, (record, _) in primary.items()
            }
            for record, meta in observed:
                ref = prefix + "package:" + record.name
                edges = {prefix + "file:" + record.name}
                is_primary = meta.name in primary and primary[meta.name][0] == record
                if is_primary and meta.name in graph:
                    edges |= {package_refs[name] for name in graph[meta.name]}
                directory = str(PurePosixPath(record.name).parent)
                for declared in meta.license_files:
                    safe_name(declared)
                    choices = [
                        directory + "/licenses/" + declared,
                        directory + "/" + declared,
                    ]
                    found = [name for name in choices if name in files]
                    if not found:
                        raise ValueError("declared license file is not bundled")
                    edges |= {prefix + "file:" + name for name in found}
                add(
                    {
                        "type": "library"
                        if meta.name != "mos-eisley"
                        else "application",
                        "bom-ref": ref,
                        "name": meta.name,
                        "version": meta.version,
                        "purl": "pkg:pypi/"
                        + meta.name
                        + "@"
                        + quote(meta.version, safe=""),
                        "licenses": _licenses(meta),
                        "properties": _properties(
                            platform=target,
                            metadata=record.name,
                            dependency_scope="resolved-runtime"
                            if is_primary and meta.name in graph
                            else "observed-bundled-metadata",
                            license_status="declared"
                            if _licenses(meta)
                            else "not-declared",
                            requires_dist=json.dumps(
                                [r.declaration for r in meta.requirements],
                                separators=(",", ":"),
                            ),
                        ),
                    },
                    edges,
                )
                dependencies[artifact_ref].add(ref)
    if len(versions) != 1 or (
        expected_version is not None and versions != {expected_version}
    ):
        raise ValueError("SBOM release version differs from selected tag")
    refs = set(components) | {root_ref}
    if any(not edges <= refs for edges in dependencies.values()):
        raise ValueError("dangling SBOM relationship")
    payload: Component = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "tools": {
                "components": [
                    {"type": "application", "name": "mos-release-sbom", "version": "1"}
                ]
            },
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": "mos-eisley",
                "version": project.version,
                "licenses": _licenses(project),
                "properties": _properties(
                    source_commit=commit,
                    release_version=next(iter(versions)),
                    wheel_metadata_sha256=wheel_record.sha256,
                ),
            },
            "properties": _properties(
                coverage=(
                    "release-payloads-and-declared-runtime; embedded-PYZ-is-opaque; "
                    "host-OS-and-external-clients-excluded"
                )
            ),
        },
        "components": [components[k] for k in sorted(components)],
        "dependencies": [
            {"ref": k, "dependsOn": sorted(dependencies[k])}
            for k in sorted(dependencies)
        ],
    }
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    payload["serialNumber"] = "urn:uuid:" + str(
        uuid.uuid5(uuid.NAMESPACE_URL, commit + ":" + identity)
    )
    if len(json.dumps(payload).encode()) > MAX_BOM:
        raise ValueError("release SBOM exceeds bound")
    return payload


def validate_sbom(root: Path, commit: str, version: str | None = None) -> None:
    path = root / "release-sbom.cdx.json"
    regular(path, MAX_BOM)
    if _json(path.read_bytes()) != build_sbom(root, commit, version):
        raise ValueError("SBOM completeness or artifact binding mismatch")


def _host_target() -> str:
    system = {"Darwin": "macos", "Linux": "linux"}.get(host_platform.system())
    machine = {"arm64": "aarch64", "aarch64": "aarch64", "x86_64": "x86_64"}.get(
        host_platform.machine()
    )
    target = str(system) + "-" + str(machine)
    if target not in PLATFORMS:
        raise ValueError("unsupported native inventory build host")
    return target


def record_runtime(destination: Path, kind: str, version: str, commit: str) -> None:
    if (
        kind not in ("application", "bootstrap")
        or host_platform.python_version() != PYTHON_VERSION
    ):
        raise ValueError("native build must use the pinned managed interpreter")
    project_version(version)
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("invalid native inventory source")
    license_source = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    regular(license_source, 512 * 1024)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(license_source, destination / "python-runtime-LICENSE.txt")
    value = {
        "schema": 1,
        "kind": kind,
        "source_commit": commit,
        "platform": _host_target(),
        "version": version,
        "python_implementation": host_platform.python_implementation(),
        "python_version": host_platform.python_version(),
        "requirements_sha256": file_digest(Path("requirements.runtime.txt")),
        "python_license_sha256": file_digest(
            destination / "python-runtime-LICENSE.txt"
        ),
    }
    (destination / "mos-runtime.json").write_text(
        json.dumps(value, sort_keys=True) + "\n"
    )


def verify_runtime(executable: Path, facts_path: Path, kind: str) -> None:
    facts = _json(facts_path.read_bytes())
    command = (
        [str(executable), "setup", "--json"]
        if kind == "application"
        else [str(executable), "--runtime-info"]
    )
    result = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=30
    )
    observed = _json(result.stdout.encode())
    python = _object(observed.get("python_runtime"))
    if (
        python.get("implementation") != facts["python_implementation"]
        or python.get("version") != facts["python_version"]
        or observed.get("platform") != facts["platform"]
        or str(observed.get("version"))
        not in (facts["version"], project_version(str(facts["version"])))
    ):
        raise ValueError("actual frozen runtime differs from inventory")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("generate", "check", "record-runtime", "verify-runtime")
    )
    parser.add_argument("--artifacts", type=Path, default=Path("dist"))
    parser.add_argument("--commit")
    parser.add_argument("--version")
    parser.add_argument("--kind", choices=("application", "bootstrap"))
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    if args.action in ("generate", "check"):
        if args.commit is None:
            parser.error("--commit is required")
        if args.action == "generate":
            bom = build_sbom(args.artifacts, args.commit, args.version)
            output = args.artifacts / "release-sbom.cdx.json"
            if output.exists() or output.is_symlink():
                regular(output, MAX_BOM)
            output.write_text(json.dumps(bom, sort_keys=True, indent=2) + "\n")
        validate_sbom(args.artifacts, args.commit, args.version)
    else:
        if args.destination is None or args.kind is None:
            parser.error("--destination and --kind are required")
        if args.action == "record-runtime":
            if args.commit is None or args.version is None:
                parser.error("--commit and --version are required")
            record_runtime(args.destination, args.kind, args.version, args.commit)
        else:
            if args.executable is None:
                parser.error("--executable is required")
            verify_runtime(
                args.executable, args.destination / "mos-runtime.json", args.kind
            )
    print("Release SBOM: " + args.action + " passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
