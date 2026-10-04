"""Active recorded session timers; the terminal owns every admission and dispatch."""

import math
from collections.abc import Callable

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_loop_commands import loop_status


class ActiveSessionTimers:
    """A bounded monotonic waiter wakes the existing owner, never a second worker."""

    poll_seconds = 1.0

    def __init__(
        self,
        controller: RuntimeConversationController,
        emit: Callable[[dict[str, object]], None],
    ) -> None:
        self.controller = controller
        self.emit = emit
        self.opened = False
        self.last_clock: float | None = None

    def open(self) -> None:
        if self.opened:
            raise ValueError("This timer owner is already open.")
        self.controller.claim_schedule_timers(self)
        self.opened = True

    @property
    def qualified(self) -> bool:
        return (
            self.opened
            and self.controller.owns_schedule_timers(self)
            and self.controller.schedule_observer is not None
            and self.controller.task_scope is None
        )

    def delay(self, *, busy: bool = False) -> float | None:
        """Recheck wall-clock deadlines at most one second apart using async sleep."""
        records = [
            s for s in self.controller.state.schedules if s.state.status == "active"
        ]
        if not self.qualified or not records:
            return None
        if busy or not self.controller.schedule_timer_idle:
            return self.poll_seconds
        now = self.controller.goal_clock()
        if not math.isfinite(now) or now < 0:
            return 0
        return min(
            self.poll_seconds,
            max(
                0.0,
                min(min(s.state.next_due_at, s.state.spec.expires_at) for s in records)
                - now,
            ),
        )

    def _pause(self, schedule_id: str, reason: str) -> None:
        self.controller.pause_schedule(
            schedule_id, expected_revision=self.controller.state.revision, reason=reason
        )

    def tick(self, *, busy: bool = False) -> tuple[str, ...]:
        """Coalesce elapsed intervals, admitting at most one intent per owner turn."""
        if not self.qualified:
            return ()
        chat = self.controller
        records = sorted(
            (s for s in chat.state.schedules if s.state.status == "active"),
            key=lambda s: (s.state.next_due_at, s.state.spec.schedule_id),
        )
        if not records:
            return ()
        now = chat.goal_clock()
        invalid_clock = not math.isfinite(now) or now < 0
        backwards = self.last_clock is not None and now < self.last_clock
        if not invalid_clock:
            self.last_clock = now
        changed = False
        for record in records:
            state, spec = record.state, record.state.spec
            if invalid_clock or backwards or now < state.last_seen_at:
                self._pause(
                    spec.schedule_id,
                    "Clock changed unsafely; explicit resume required.",
                )
                changed = True
                continue
            goal = chat.current_goal
            if (
                goal is None
                or goal.status != "working"
                or goal.goal_id != spec.binding.goal_id
                or goal.definition.sha256 != spec.binding.goal_definition_sha256
            ):
                self._pause(
                    spec.schedule_id,
                    "Goal stopped or changed; explicit resume required.",
                )
                changed = True
                continue
            if busy:
                continue
            safe = chat.schedule_timer_idle
            if not (
                now >= spec.expires_at
                or now >= state.next_due_at
                or ((state.pending_timer or state.pending_events) and safe)
            ):
                continue
            # Queued user work wins; do not repeatedly write a due timer while busy.
            if not safe:
                continue
            try:
                operation = chat.admit_schedule(
                    spec.schedule_id, expected_revision=chat.state.revision
                )
            except (ValueError, OSError):
                if chat.persistence_broken:
                    raise
                self._pause(
                    spec.schedule_id,
                    "Timer admission rejected; check scope and limits before resume.",
                )
                changed = True
                continue
            changed = True
            if operation is not None:
                loop_status(chat, spec.schedule_id, self.emit)
                return (operation,)
        if changed:
            # The clock may be invalid: status rendering must not encode a NaN.
            if not invalid_clock:
                loop_status(chat, None, self.emit)
            else:
                self.emit(
                    {
                        "type": "conversation.unavailable",
                        "text": (
                            "Timers paused: invalid clock; explicit resume required."
                        ),
                    }
                )
        return ()

    def pause(self, reason: str) -> None:
        """A failed owner turn stops future ticks without refund or implicit retry."""
        if (
            not self.opened
            or not self.controller.owns_schedule_timers(self)
            or self.controller.persistence_broken
        ):
            return
        for record in self.controller.state.schedules:
            if record.state.status == "active":
                self._pause(record.state.spec.schedule_id, reason)

    def close(self) -> None:
        """Pause clean schedules once; never replay persisted uncertainty."""
        if not self.opened:
            return
        self.opened = False
        self.controller.release_schedule_timers(self)
