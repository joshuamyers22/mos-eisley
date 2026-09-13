"""Two explicit host approvals around the owned brokered review lifecycle."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from typing import Protocol

from mos_eisley.providers.openai_spend import CountedTransport
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerCriticPreview,
    ControllerJudgePreview,
)
from mos_eisley.run.review_verdict import RetainedReviewResult

ApprovalPreview = ControllerCriticPreview | ControllerJudgePreview


class ReviewApprovalUI(Protocol):
    async def approve(self, preview: ApprovalPreview) -> str | None:
        """Show exact content and limits; return the user's hash or explicit decline."""
        ...

    async def show_result(self, result: RetainedReviewResult) -> None: ...


class BrokeredReviewApprovalFlow:
    """One-use host flow; transports and conformance admission remain host duties."""

    def __init__(self, controller: BrokeredReviewController, ui: ReviewApprovalUI):
        self._controller = controller
        self._ui = ui
        self._started = False
        self._judge_preview: ControllerJudgePreview | None = None

    @property
    def judge_preview(self) -> ControllerJudgePreview | None:
        """Trusted host output for independent retention and later inspection."""
        return self._judge_preview

    async def run(
        self,
        *,
        critic_transports: tuple[CountedTransport, ...],
        critic_containers: tuple[OfflineContainer, ...],
        judge_transport: CountedTransport,
        judge_container: OfflineContainer,
    ) -> RetainedReviewResult | None:
        if self._started or self._controller.phase != "prepared":
            raise ValueError("review approval flow requires a fresh controller")
        self._started = True
        controller = self._controller
        owns_controller = False
        try:
            preview = controller.preview
            approval = await self._ui.approve(preview)
            # Another host flow may have consumed this controller during the prompt.
            if controller.phase != "prepared":
                raise ValueError("review controller changed while awaiting approval")
            if approval is None:
                controller.cancel()
                return None
            if approval != preview.sha256:
                raise ValueError("exact critic approval required")
            owns_controller = True
            deadline = (
                asyncio.get_running_loop().time()
                + controller.authorization.total_seconds
            )
            judge = await controller.run_critics(
                approved_controller_sha256=approval,
                transports=critic_transports,
                containers=critic_containers,
            )
            self._judge_preview = judge
            start = controller.start
            assert start is not None
            remaining = min(
                deadline - asyncio.get_running_loop().time(),
                (start.expires_at - datetime.now(UTC)).total_seconds(),
            )
            if remaining <= 0:
                raise TimeoutError("review deadline expired before judge approval")
            async with asyncio.timeout(remaining):
                judge_approval = await self._ui.approve(judge)
            if judge_approval is None:
                controller.cancel()
                return None
            if judge_approval != judge.sha256:
                raise ValueError("exact judge approval required")
            result = await controller.run_judge(
                approved_preview_sha256=judge_approval,
                transport=judge_transport,
                container=judge_container,
            )
            await self._ui.show_result(result)
            return result
        except BaseException:
            # Active controller calls own and await their children before raising.
            # A stale competing flow cannot cancel another flow's judge pause.
            if controller.phase == "prepared" or (
                owns_controller and controller.phase == "awaiting_judge"
            ):
                with suppress(OSError, ValueError):
                    controller.cancel()
            raise
