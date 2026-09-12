"""Inspect local advisory guidance without attaching it to a project."""

import argparse
import json
from pathlib import Path

from mos_eisley.memory_cli import safe_text
from mos_eisley.project_guidance import inspect_guidance


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument("--descriptor", type=Path, required=True)
    command.add_argument("--markdown", type=Path, required=True)
    command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    snapshot = inspect_guidance(args.workspace, args.descriptor, args.markdown)
    event = {
        "type": "guidance.inspected",
        "snapshot_sha256": snapshot.sha256,
        "snapshot": snapshot.model_dump(mode="json"),
    }
    if args.json:
        print(json.dumps(event, ensure_ascii=True))
    else:
        descriptor = snapshot.descriptor
        print(
            safe_text(
                f"Advisory guidance: {descriptor.template_id} {descriptor.version}\n"
                f"Workspace: {snapshot.workspace}\n"
                f"Descriptor: {snapshot.descriptor_path}\n"
                f"Markdown: {snapshot.markdown_path}\n"
                f"Declared source revision: {descriptor.source_revision}\n"
                f"Content SHA-256: {descriptor.content_sha256}\n"
                f"Snapshot SHA-256: {snapshot.sha256}\n"
                "Status: inspected, unbound. No guidance attached to this project."
            )
        )
        for rule, location in zip(descriptor.rules, snapshot.rules, strict=True):
            print(
                safe_text(
                    f"\n{rule.id} (advisory), "
                    f"characters {location.character_start}:{location.character_end}\n"
                    f"{rule.text}\nApplies when: {rule.applies_when}\n"
                    f"Rationale: {rule.rationale}\n"
                    "Checks:\n" + "\n".join(rule.checks)
                )
            )
        print(safe_text("\nComplete Markdown:\n" + snapshot.markdown))
    return 0
