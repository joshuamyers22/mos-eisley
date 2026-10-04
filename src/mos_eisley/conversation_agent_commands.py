"""Shared /agent and /subagents inspection; no steering or lifecycle controls."""

from collections.abc import Callable
from typing import Literal

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_agents import AgentInspection


def inspection_text(view: AgentInspection) -> str:
    lines = [f"Authorized children — controller revision {view.snapshot.revision}."]
    if not view.snapshot.children:
        lines.append("No authorized child records.")
    for child in view.snapshot.children:
        lines.append(f"{child.child_id}: {child.role}; {child.state}.")
        assignment = child.assignment
        if assignment is None:
            lines.append(
                "Independent review: operational status only; evidence sealed."
            )
            continue
        lines.extend(
            (
                f"Assignment: {assignment.objective}",
                f"Task {assignment.task_id}; parent task {assignment.parent_task_id}.",
                f"Route {assignment.provider}/{assignment.model}; "
                f"effort {assignment.effort or 'default'}.",
                f"Workspace {assignment.workspace}; "
                f"worktree {assignment.worktree or 'none'}.",
                f"Assignment {'current' if child.assignment_current else 'stale'}; "
                f"verification {child.verification}.",
            )
        )
        usage = child.usage
        if usage is None:
            lines.append(
                "Usage/spend unavailable; retained allowance is not measured usage."
            )
        else:
            ceiling = assignment.allowance
            lines.append(
                f"Usage input {usage.input_bytes}/{ceiling.input_bytes} bytes; "
                f"output {usage.output_bytes}/{ceiling.output_bytes} bytes; "
                f"attempts {usage.attempts}/{ceiling.attempts}; "
                f"spend {usage.cost_microusd}/{ceiling.cost_microusd} microUSD; "
                f"uncertain effects {usage.uncertain_effects}."
            )
        lines.append("Unresolved: " + ("; ".join(child.unresolved) or "none recorded"))
        lines.append(
            "Report: " + (child.report.availability if child.report else "missing")
        )
    if view.report_status != "not_requested":
        lines.append(f"Selected report: {view.report_status}.")
    if view.report is not None:
        lines.append("Implementation report (creator integration remains required):")
        lines.append(view.report.summary)
        lines.extend("Evidence: " + item for item in view.report.evidence)
        lines.extend("Unresolved: " + item for item in view.report.unresolved)
    return "\n".join(lines)


def agent_command(
    controller: RuntimeConversationController,
    line: str,
    emit: Callable[[dict[str, object]], None],
) -> Literal["accepted", "rejected"]:
    try:
        args = line.split()
        if (
            len(line) > 200
            or "\n" in line
            or not args
            or args[0] not in {"/agent", "/subagents"}
        ):
            raise ValueError("Use /agent [CHILD_ID] [--json] or /subagents.")
        positional = [a for a in args[1:] if a != "--json"]
        if len(positional) > 1 or args.count("--json") > 1:
            raise ValueError("Inspection accepts one child ID and optional --json.")
        view = controller.inspect_agents(positional[0] if positional else None)
        emit(
            {
                "type": "conversation.agents",
                "inspection": view.model_dump(mode="json"),
                "text": view.model_dump_json()
                if "--json" in args
                else inspection_text(view),
            }
        )
    except (OSError, ValueError):
        # Adapter error messages may contain private paths or sealed content.
        message = (
            "Implementation-agent inspection requires the qualified child controller; "
            "no inspection source is connected."
            if controller.child_inspection is None
            else "Agent inspection unavailable: invalid command, unauthorized scope, "
            "stale view or unavailable retained evidence."
        )
        emit({"type": "conversation.unavailable", "text": message})
        return "rejected"
    return "accepted"
