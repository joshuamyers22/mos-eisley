"""Shared explicit fork/side controls; no ambient context or child execution."""

from collections.abc import Callable
from typing import Literal

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.core.agent import AgentFailure


def positions(text: str) -> tuple[int, ...]:
    if text == "-":
        return ()
    try:
        values = tuple(int(value) for value in text.split(","))
    except ValueError:
        raise ValueError(
            "Use ordered message positions such as 0,2 or - for no context."
        ) from None
    if any(v < 0 or v > 15 for v in values) or values != tuple(sorted(set(values))):
        raise ValueError("Select unique ordered positions from 0 through 15.")
    return values


class BranchCommands:
    def __init__(
        self,
        controller: RuntimeConversationController,
        emit: Callable[[dict[str, object]], None],
    ):
        self.controller, self.emit = controller, emit

    async def execute(
        self, line: str, *, on_side_started: Callable[[], None] | None = None
    ) -> Literal["accepted", "queued", "rejected"]:
        try:
            if len(line) > 8000 or line.count("\n") >= 256:
                raise ValueError("Branch controls exceed ordinary input limits.")
            args = line.split(maxsplit=2)
            command = args[0]
            if command == "/fork":
                if len(args) == 1 or args[1:] == ["status"]:
                    self.status()
                elif args[1:] == ["revalidate"]:
                    self.controller.revalidate_fork()
                    self.status()
                else:
                    if "worktree" in line:
                        raise ValueError(
                            "Isolated forks require the qualified worktree broker."
                        )
                    boundary = int(args[1])
                    selected = positions(args[2]) if len(args) > 2 else (boundary,)
                    child = self.controller.create_fork(
                        selected,
                        boundary=boundary,
                        expected_revision=self.controller.state.revision,
                    )
                    self.emit(
                        {
                            "type": "conversation.fork",
                            "session_id": child.session_id,
                            "origin": child.fork_origin.model_dump(mode="json")
                            if child.fork_origin is not None
                            else None,
                            "budget": child.branch_budget.model_dump(mode="json")
                            if child.branch_budget is not None
                            else None,
                            "text": (
                                f"Fork saved: {child.session_id}. "
                                "Resume explicitly with "
                                f"mos resume {child.session_id}. "
                                "Selected context only; filesystem effects remain. "
                                "Parent permanently reserves the branch allowance."
                            ),
                        }
                    )
            elif command == "/side":
                if len(args) == 1 or args[1:] == ["status"]:
                    self.status()
                elif len(args) == 3 and args[1] == "attach":
                    self.controller.attach_side(args[2])
                    self.status()
                    return "queued"
                elif len(args) == 3 and args[1] == "discard":
                    self.controller.discard_side(args[2])
                    self.emit(
                        {
                            "type": "conversation.side",
                            "text": "Transient side answer discarded; "
                            "accounting receipt retained.",
                        }
                    )
                elif len(args) == 3:
                    answer = await self.controller.ask_side(
                        args[2],
                        positions(args[1]),
                        expected_revision=self.controller.state.revision,
                        on_started=on_side_started,
                    )
                    self.emit(
                        {
                            "type": "conversation.side",
                            "receipt": answer.receipt.model_dump(mode="json"),
                            "answer": answer.answer,
                            "text": (
                                f"Side answer {answer.receipt.side_id} "
                                "(transient; /side attach ID copies it explicitly):\n"
                                f"{answer.answer}"
                            ),
                        }
                    )
                else:
                    raise ValueError(
                        "Use /side POSITIONS QUESTION, "
                        "/side attach ID, discard ID or status."
                    )
            else:
                raise ValueError(
                    "Use /fork BOUNDARY [POSITIONS] or /side POSITIONS QUESTION."
                )
        except (AgentFailure, OSError, ValueError) as error:
            if self.controller.persistence_broken:
                raise
            self.emit({"type": "conversation.unavailable", "text": str(error)})
            return "rejected"
        return "accepted"

    def status(self) -> None:
        state = self.controller.state
        budget = state.branch_budget
        description = (
            "Fork/side conversational aids; "
            "no execution or independent-review authority."
        )
        if state.fork_origin is not None:
            source = state.fork_origin.context
            selected = ",".join(str(m.position) for m in source.messages) or "none"
            description += (
                f"\nParent {source.parent_session_id}; "
                f"revision {source.source_revision}; "
                f"boundary {source.boundary}; selected positions {selected}."
            )
        if budget is not None:
            description += (
                f"\nAttempts {budget.ledger.attempts}/{budget.ceiling.attempts}; "
                f"input {budget.ledger.input_bytes}/"
                f"{budget.ceiling.input_bytes} bytes; "
                f"output {budget.ledger.output_bytes}/"
                f"{budget.ceiling.output_bytes} bytes; "
                f"uncertainty {budget.ledger.uncertain_effects}."
            )
        for receipt in state.forks:
            description += (
                f"\nFork {receipt.child_session_id}: {receipt.state}; "
                f"source revision {receipt.source_revision}."
            )
        for receipt in state.sides:
            availability = (
                "available"
                if self.controller.side_answer_available(receipt.side_id)
                else "content unavailable"
            )
            description += (
                f"\nSide {receipt.side_id}: {receipt.state}; {availability}; "
                f"attached {receipt.attached_position}."
            )
        self.emit(
            {
                "type": "conversation.branches",
                "origin": None
                if state.fork_origin is None
                else state.fork_origin.model_dump(mode="json"),
                "budget": None if budget is None else budget.model_dump(mode="json"),
                "forks": [f.model_dump(mode="json") for f in state.forks],
                "sides": [s.model_dump(mode="json") for s in state.sides],
                "text": description,
            }
        )
