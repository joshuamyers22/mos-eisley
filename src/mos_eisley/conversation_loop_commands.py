"""Explicit /loop controls; no timers, event ingress or model dispatch."""

from collections.abc import Callable
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_branch_controller import observe_branch_workspace
from mos_eisley.conversation_goal import merge_ledger
from mos_eisley.conversation_schedule import InertScheduleSpec, ScheduleBinding
from mos_eisley.conversation_schedule_controller import (
    scheduled_branch_exposure,
    scheduled_goal_exposure,
)
from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    Text,
    canonical_bytes,
    digest,
)
from mos_eisley.task_state import ResourceCeiling

HELP = (
    "/loop [status [ID]] [--json], /loop create JSON, /loop cancel ID, "
    "/loop resume ID. Creation JSON requires schedule_id, task_id, prompt, "
    "interval_seconds, expires_in_seconds, maximum_fires, input_bytes, output_bytes. "
    "cadence defaults to fixed; dynamic requires minimum_interval_seconds and "
    "maximum_interval_seconds. Timers run only in an active recorded session."
)


class LoopCreate(Contract):
    schedule_id: Identifier
    task_id: Identifier
    prompt: Text
    interval_seconds: Annotated[int, Field(ge=1, le=86400)]
    expires_in_seconds: Annotated[int, Field(ge=1, le=86400)]
    maximum_fires: Annotated[int, Field(ge=1, le=16)]
    input_bytes: Annotated[int, Field(ge=1, le=1_000_000)]
    output_bytes: Annotated[int, Field(ge=1, le=1_000_000)]
    cadence: Literal["fixed", "dynamic"] = "fixed"
    minimum_interval_seconds: Annotated[int, Field(ge=1, le=86400)] | None = None
    maximum_interval_seconds: Annotated[int, Field(ge=1, le=86400)] | None = None

    @model_validator(mode="after")
    def explicit_cadence(self) -> Self:
        if not self.prompt.strip():
            raise ValueError("Loop task text cannot be blank.")
        if self.cadence == "dynamic" and (
            self.minimum_interval_seconds is None
            or self.maximum_interval_seconds is None
        ):
            raise ValueError("Dynamic cadence requires both explicit interval bounds.")
        minimum = self.minimum_interval_seconds or self.interval_seconds
        maximum = self.maximum_interval_seconds or self.interval_seconds
        if not minimum <= self.interval_seconds <= maximum:
            raise ValueError("Interval must be within its explicit bounds.")
        if self.cadence == "fixed" and (
            minimum != self.interval_seconds or maximum != self.interval_seconds
        ):
            raise ValueError("Fixed cadence bounds must equal the selected interval.")
        return self


class RecordedLoopPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["recorded_text_only"] = "recorded_text_only"
    cassette_sha256: Digest
    goal_definition_sha256: Digest
    automatic_dispatch: Literal[True] = True
    external_ingress: Literal[False] = False
    paid_calls: Literal[False] = False


def recorded_loop_observer(
    controller: RuntimeConversationController,
) -> Callable[[InertScheduleSpec], ScheduleBinding]:
    """CLI-owned read-only workspace observation; cannot grant execution authority."""

    def observe(spec: InertScheduleSpec) -> ScheduleBinding:
        goal = controller.current_goal
        if (
            goal is None
            or controller.task_scope is not None
            or controller.state.mode != "recorded_conversation"
        ):
            raise ValueError(
                "Recorded loops require a selected goal and recorded scope."
            )
        policy = RecordedLoopPolicy(
            cassette_sha256=controller.state.cassette_sha256,
            goal_definition_sha256=goal.definition.sha256,
        )
        return ScheduleBinding(
            owner_uid=controller.state.owner_uid,
            session_id=controller.state.session_id,
            workspace_sha256=digest(controller.state.workspace.encode()),
            revision_sha256=observe_branch_workspace(controller.state.workspace),
            policy_sha256=digest(canonical_bytes(policy)),
            goal_id=goal.goal_id,
            goal_definition_sha256=goal.definition.sha256,
            task_id=spec.binding.task_id,
        )

    return observe


def _create(
    controller: RuntimeConversationController, create: LoopCreate, revision: int
) -> str:
    goal = controller.current_goal
    if goal is None or controller.schedule_observer is None:
        raise ValueError(
            "Loop creation requires a working goal and trusted scope observer."
        )
    # Identity/policy/revision fields cannot be supplied by command JSON.
    binding = ScheduleBinding(
        owner_uid=controller.state.owner_uid,
        session_id=controller.state.session_id,
        workspace_sha256=digest(controller.state.workspace.encode()),
        revision_sha256="0" * 64,
        policy_sha256="0" * 64,
        goal_id=goal.goal_id,
        goal_definition_sha256=goal.definition.sha256,
        task_id=create.task_id,
    )
    spec = InertScheduleSpec(
        schedule_id=create.schedule_id,
        binding=binding,
        prompt=create.prompt,
        cadence=create.cadence,
        interval_seconds=create.interval_seconds,
        minimum_interval_seconds=create.minimum_interval_seconds
        or create.interval_seconds,
        maximum_interval_seconds=create.maximum_interval_seconds
        or create.interval_seconds,
        expires_at=controller.goal_clock() + create.expires_in_seconds,
        maximum_fires=create.maximum_fires,
        ceiling=ResourceCeiling(
            input_bytes=create.input_bytes,
            output_bytes=create.output_bytes,
            attempts=create.maximum_fires,
            cost_microusd=0,
            correction_cycles=0,
            review_rounds=0,
        ),
    )
    binding = controller.read_schedule_binding(spec)
    spec = spec.model_copy(update={"binding": binding})
    controller.add_schedule(spec, expected_revision=revision)
    return spec.schedule_id


def loop_status(
    controller: RuntimeConversationController,
    selected: str | None,
    emit: Callable[[dict[str, object]], None],
    *,
    as_json: bool = False,
) -> None:
    snapshot = controller.state
    records = [
        s
        for s in snapshot.schedules
        if selected is None or s.state.spec.schedule_id == selected
    ]
    if selected is not None and not records:
        raise ValueError("Schedule is not retained in this session.")
    now = controller.goal_clock()
    lines = ["Loop schedules. Recorded timers run only in an active qualified session."]
    items: list[dict[str, object]] = []
    if not records:
        lines.append(
            "No retained schedules. /loop help shows explicit creation fields."
        )
    for record in records:
        state, spec = record.state, record.state.spec
        ledger = state.ledger
        goal = next(g for g in snapshot.goals if g.goal_id == spec.binding.goal_id)
        aggregate = merge_ledger(
            state.aggregate_exposure, scheduled_goal_exposure(snapshot, goal.goal_id)
        )
        remaining = {
            key: max(0, getattr(spec.ceiling, key) - getattr(ledger, key))
            for key in ResourceCeiling.model_fields
        }
        task_remaining = {
            key: max(0, getattr(goal.definition.ceiling, key) - getattr(aggregate, key))
            for key in ResourceCeiling.model_fields
        }
        unresolved = [
            dict(
                operation_id=f.operation_id,
                state=f.state,
                message_position=b.message_position,
                queue_state=snapshot.entries[b.message_position].status,
            )
            for b, f in zip(record.queue_bindings, state.fires, strict=True)
            if f.state in {"reserved", "uncertain"}
        ]
        branch_remaining = None
        if snapshot.branch_budget is not None:
            branch_exposure = scheduled_branch_exposure(snapshot)
            branch_remaining = {
                key: max(
                    0,
                    getattr(snapshot.branch_budget.ceiling, key)
                    - getattr(branch_exposure, key),
                )
                for key in ResourceCeiling.model_fields
            }
        expiry_remaining = max(0.0, spec.expires_at - now)
        items.append(
            {
                "record": record.model_dump(mode="json"),
                "remaining": remaining,
                "task_remaining": task_remaining,
                "remaining_fires": spec.maximum_fires - len(state.fires),
                "expires_in_seconds": expiry_remaining,
                "unresolved": unresolved,
                "goal_status": goal.status,
                "branch_remaining": branch_remaining,
            }
        )
        lines.extend(
            (
                f"{spec.schedule_id}: {state.status}; task {spec.binding.task_id}; "
                f"goal {spec.binding.goal_id} ({goal.status}).",
                f"Task: {spec.prompt}",
                f"Cadence {spec.cadence}: {state.effective_interval_seconds}s; "
                f"bounds {spec.minimum_interval_seconds}–"
                f"{spec.maximum_interval_seconds}s; "
                f"history {list(state.cadence_history)}.",
                f"Next due {state.next_due_at}; expires {spec.expires_at} "
                f"({expiry_remaining:g}s left).",
                f"Fires {len(state.fires)}/{spec.maximum_fires}; "
                f"remaining {spec.maximum_fires - len(state.fires)}.",
                f"Remaining input {remaining['input_bytes']} "
                f"bytes; output {remaining['output_bytes']} "
                f"bytes; attempts {remaining['attempts']}; paid "
                f"allowance 0 microUSD.",
                f"Task remaining input {task_remaining['input_bytes']} "
                f"bytes; output {task_remaining['output_bytes']} "
                f"bytes; attempts {task_remaining['attempts']}.",
                f"Task remaining cost {task_remaining['cost_microusd']} microUSD; "
                f"corrections {task_remaining['correction_cycles']}; "
                f"reviews {task_remaining['review_rounds']}; "
                f"uncertainty {aggregate.uncertain_effects}.",
                f"Exposure input {ledger.input_bytes}; output "
                f"{ledger.output_bytes}; attempts {ledger.attempts}; "
                f"uncertainty {ledger.uncertain_effects}.",
                f"Pending timer {state.pending_timer}; events "
                f"{state.pending_events}; reason: {state.reason}",
            )
        )
        for receipt in state.ingress_receipts:
            lines.append(
                f"External source {receipt.source_id}: latest sequence "
                f"{receipt.sequence}; payload omitted ({receipt.payload_bytes} bytes)."
            )
        if branch_remaining is not None:
            lines.append(
                f"Fork remaining input {branch_remaining['input_bytes']} bytes; "
                f"output {branch_remaining['output_bytes']} bytes; "
                f"attempts {branch_remaining['attempts']}."
            )
        if not expiry_remaining:
            lines.append("Expired by current clock; dispatch is prohibited.")
        for item in unresolved:
            lines.append(
                f"Unresolved {item['operation_id']}: {item['state']}; "
                f"message {item['message_position']} ({item['queue_state']})."
            )
    event: dict[str, object] = {
        "type": "conversation.loop",
        "revision": snapshot.revision,
        "schedules": items,
        "automatic_dispatch": (
            controller.schedule_timer_active
            and controller.schedule_observer is not None
            and controller.task_scope is None
            and controller.state.mode == "recorded_conversation"
        ),
    }
    if as_json:
        import json

        event["text"] = json.dumps(event, sort_keys=True, ensure_ascii=False)
    else:
        event["text"] = "\n".join(lines)
    emit(event)


def loop_command(
    controller: RuntimeConversationController,
    line: str,
    emit: Callable[[dict[str, object]], None],
) -> Literal["accepted", "rejected"]:
    try:
        if len(line) > 8000 or "\n" in line or "\r" in line:
            raise ValueError("Loop controls require one bounded typed line.")
        args = line.split(maxsplit=2)
        if not args or args[0] != "/loop":
            raise ValueError("Use /loop controls.")
        revision = controller.state.revision
        action = args[1] if len(args) > 1 else "status"
        payload = args[2] if len(args) > 2 else None
        if action == "help" and payload is None:
            emit({"type": "conversation.loop", "schedules": [], "text": HELP})
            return "accepted"
        selected = None
        as_json = False
        if action == "create" and payload is not None:
            with controller.schedule_reads.operation():
                selected = _create(
                    controller, LoopCreate.model_validate_json(payload), revision
                )
        elif (
            action in {"cancel", "resume"}
            and payload is not None
            and len(payload.split()) == 1
        ):
            selected = payload
            if action == "cancel":
                controller.cancel_schedule(selected, expected_revision=revision)
            else:
                controller.resume_schedule(selected, expected_revision=revision)
        elif action in {"status", "--json"}:
            values = [] if payload is None else payload.split()
            if action == "--json":
                if payload is not None:
                    raise ValueError("Use /loop status ID --json.")
                values = ["--json"]
            if values.count("--json") > 1:
                raise ValueError("Duplicate JSON option.")
            as_json = "--json" in values
            values = [value for value in values if value != "--json"]
            if len(values) > 1:
                raise ValueError("Inspection accepts at most one schedule ID.")
            selected = values[0] if values else None
        else:
            raise ValueError("Unrecognized loop control.")
        loop_status(controller, selected, emit, as_json=as_json)
    except (ValueError, OSError):
        if controller.persistence_broken:
            raise
        emit(
            {
                "type": "conversation.unavailable",
                "text": (
                    "Loop control rejected. Check explicit fields/limits, "
                    "working goal, "
                    "trusted workspace scope and unresolved exposure. "
                    "/loop help shows syntax."
                ),
            }
        )
        return "rejected"
    return "accepted"
