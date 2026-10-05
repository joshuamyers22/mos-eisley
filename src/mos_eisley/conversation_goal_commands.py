"""Explicit local goal controls shared by the TUI and text terminals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal, cast

from pydantic import Field

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_goal import GoalDefinition
from mos_eisley.core.models import Contract


class GoalEdit(Contract):
    expected_revision: Annotated[int, Field(ge=1, le=16)]
    definition: GoalDefinition


def goal_command(
    controller: RuntimeConversationController,
    line: str,
    emit: Callable[[dict[str, object]], None],
) -> Literal["accepted", "rejected"] | None:
    if line.split(maxsplit=1)[:1] != ["/goal"]:
        return None
    try:
        if len(line) > 8000 or line.count("\n") >= 256:
            raise ValueError("Goal controls exceed the ordinary input limits.")
        args = line.split(maxsplit=2)
        action = args[1] if len(args) > 1 else "status"
        payload = args[2] if len(args) > 2 else None
        if action == "create" and payload is not None:
            definition = GoalDefinition.model_validate_json(payload)
            controller.create_goal(definition)
        elif action == "new" and payload is not None:
            controller.create_goal(
                GoalDefinition(
                    objective=payload,
                    success_criteria=(payload,),
                    remaining_work=(payload,),
                )
            )
        elif action == "edit" and payload is not None:
            edit = GoalEdit.model_validate_json(payload)
            controller.edit_goal(
                edit.definition, expected_revision=edit.expected_revision
            )
        elif action in {"pause", "resume", "cancel", "clear"} and payload is None:
            controller.goal_control(
                cast(Literal["pause", "resume", "cancel", "clear"], action)
            )
        elif action == "check" and payload is None:
            controller.check_goal()
        elif action not in {"status", "history"} or payload is not None:
            raise ValueError(
                "Use /goal new TEXT, create JSON, edit JSON, "
                "status, history, check, pause, resume, cancel or clear."
            )
    except (ValueError, OSError) as error:
        # Input errors are recoverable; persistence failures are fatal and set _broken.
        if controller.persistence_broken:
            raise
        emit({"type": "conversation.unavailable", "text": str(error)})
        return "rejected"
    goal = controller.current_goal
    emit(
        {
            "type": "conversation.goal",
            "revision": controller.state.revision,
            "active_goal_id": controller.state.active_goal_id,
            "goal": None if goal is None else goal.model_dump(mode="json"),
            "history": [g.model_dump(mode="json") for g in controller.state.goals]
            if action == "history"
            else [],
            "text": (
                "\n\n".join(
                    g.describe(controller.goal_clock()) for g in controller.state.goals
                )
                or "No retained goals."
            )
            if action == "history"
            else goal.describe(controller.goal_clock())
            if goal is not None
            else "No active goal; retained history remains available.",
        }
    )
    return "accepted"
