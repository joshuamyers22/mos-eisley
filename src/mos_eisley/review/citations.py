"""Deterministic, bounded citation views for exact review evidence."""

from __future__ import annotations

import json
import re
from typing import Literal, NamedTuple

from mos_eisley.core.models import (
    Brief,
    CitationUnit,
    CriticRequest,
    Finding,
    digest,
)

_HUNK = re.compile(
    r"^@@ -\d+(?:,(?P<old_count>\d+))? "
    r"\+\d+(?:,(?P<new_count>\d+))? @@"
)
_MAX_HUNKS = 1024
CitationView = Literal["raw", "before", "after"]


class _ResolvedUnit(NamedTuple):
    descriptor: CitationUnit
    text: str


def _unit(view: CitationView, locator: str, text: str) -> _ResolvedUnit:
    identity = json.dumps(
        {"locator": locator, "text": text, "view": view},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _ResolvedUnit(
        CitationUnit(
            id=f"diff.{view}.{digest(identity)}",
            view=view,
            locator=locator,
        ),
        text,
    )


def _diff_units(diff: str) -> tuple[_ResolvedUnit, ...]:
    units = [_unit("raw", "entire frozen diff, including patch markers", diff)]
    lines = diff.splitlines(keepends=True)
    old_path = "unknown"
    new_path = "unknown"
    hunk_count = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("--- "):
            old_path = line[4:].rstrip("\r\n")
        elif line.startswith("+++ "):
            new_path = line[4:].rstrip("\r\n")
        match = _HUNK.match(line)
        if match is None:
            index += 1
            continue
        hunk_count += 1
        if hunk_count > _MAX_HUNKS:
            raise ValueError("diff contains too many citation hunks")
        header = line.rstrip("\r\n")
        old_remaining = int(match.group("old_count") or "1")
        new_remaining = int(match.group("new_count") or "1")
        index += 1
        before_parts: list[str] = []
        after_parts: list[str] = []
        while old_remaining or new_remaining:
            if index >= len(lines):
                raise ValueError("unified diff hunk ends before its declared lines")
            item = lines[index]
            prefix = item[:1]
            content = item[1:]
            sides: tuple[str, ...]
            if prefix == " ":
                old_remaining -= 1
                new_remaining -= 1
                before_parts.append(content)
                after_parts.append(content)
                sides = ("before", "after")
            elif prefix == "-":
                old_remaining -= 1
                before_parts.append(content)
                sides = ("before",)
            elif prefix == "+":
                new_remaining -= 1
                after_parts.append(content)
                sides = ("after",)
            else:
                raise ValueError("unified diff hunk contains an invalid line")
            if old_remaining < 0 or new_remaining < 0:
                raise ValueError("unified diff hunk exceeds its declared lines")
            index += 1
            if index < len(lines) and lines[index].startswith("\\ "):
                for side in sides:
                    parts = before_parts if side == "before" else after_parts
                    parts[-1] = parts[-1].removesuffix("\n").removesuffix("\r")
                index += 1
        before = "".join(before_parts)
        after = "".join(after_parts)
        locator = f"hunk {hunk_count}: old={old_path}; new={new_path}; header={header}"
        if before:
            units.append(_unit("before", locator, before))
        if after:
            units.append(_unit("after", locator, after))
    return tuple(units)


def citation_units(brief: Brief) -> tuple[CitationUnit, ...]:
    """Return compact descriptors; source text remains solely in the brief."""
    return tuple(unit.descriptor for unit in _diff_units(brief.diff))


def citation_bound_request(brief: Brief, persona: str) -> CriticRequest:
    """Construct the current citation contract without changing legacy defaults."""
    return CriticRequest(
        schema_version=2,
        brief=brief,
        persona=persona,
        citation_units=citation_units(brief),
    )


def validate_citation_catalog(request: CriticRequest) -> None:
    if request.schema_version == 1:
        return
    if request.citation_units != citation_units(request.brief):
        raise ValueError("critic request citation catalog differs from its brief")


def validate_evidence(request: CriticRequest, findings: tuple[Finding, ...]) -> None:
    """Validate exact quotes under the request's versioned citation contract."""
    validate_citation_catalog(request)
    if request.schema_version == 1:
        for finding in findings:
            source: str = getattr(request.brief, finding.evidence.source)
            if (
                finding.evidence.source_unit is not None
                or finding.evidence.quote not in source
            ):
                raise ValueError("citation does not occur in its declared brief source")
        return

    resolved = {unit.descriptor.id: unit for unit in _diff_units(request.brief.diff)}
    for finding in findings:
        evidence = finding.evidence
        if evidence.source != "diff":
            source = getattr(request.brief, evidence.source)
            if evidence.source_unit is not None or evidence.quote not in source:
                raise ValueError("citation does not occur in its declared brief source")
            continue
        if evidence.source_unit is None:
            raise ValueError("schema-2 diff citation requires a source unit")
        unit = resolved.get(evidence.source_unit)
        if unit is None or evidence.quote not in unit.text:
            raise ValueError("citation does not occur in its declared source unit")
