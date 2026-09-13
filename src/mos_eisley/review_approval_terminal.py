"""Plain, asynchronous approval UI for an already admitted host review flow."""

import json
from collections.abc import Awaitable, Callable
from typing import TextIO

from mos_eisley.run.review_approval import ApprovalPreview
from mos_eisley.run.review_controller import ControllerCriticPreview
from mos_eisley.run.review_verdict import RetainedReviewResult
from mos_eisley.terminal_text import safe_label


class TerminalReviewApproval:
    """Inject cancellable terminal input; never read stdin in a detached thread."""

    def __init__(
        self, read_line: Callable[[str], Awaitable[str]], output: TextIO
    ) -> None:
        self._read_line = read_line
        self._output = output

    def _write(self, value: str) -> None:
        self._output.write(value + "\n")
        self._output.flush()

    async def approve(self, preview: ApprovalPreview) -> str | None:
        if isinstance(preview, ControllerCriticPreview):
            self._write("Review critic requests")
            for request in preview.requests:
                self._write(
                    f"  {safe_label(request.provider)} / {safe_label(request.model)}"
                )
            reserved_usd = preview.envelope.total_reserved_microusd / 1_000_000
            self._write(
                f"Maximum reserved spending: ${reserved_usd:.6f}, "
                "including the later judge allowance."
            )
            self._write(f"Approval expires: {preview.envelope.expires_at.isoformat()}.")
            policy = preview.authorization.policy
            self._write(
                f"Required quorum: {policy.min_critics} critics; "
                f"minimum providers: {policy.min_providers}."
            )
            self._write(
                "Review time limit after approval: "
                f"{preview.authorization.total_seconds:g} seconds."
            )
        else:
            self._write("Review judge request")
            self._write(
                f"  {safe_label(preview.model_request.provider)} / "
                f"{safe_label(preview.model_request.model)}"
            )
            findings = len(preview.evidence.judge_request.findings)
            self._write(f"Findings to adjudicate: {findings}.")
            self._write(
                "Uses the judge allowance already reserved. "
                "The review deadline continues while you decide."
            )
        self._write(f"Approval: {preview.sha256}")
        while True:
            try:
                answer = await self._read_line("Type show, approve <hash>, or cancel: ")
            except EOFError:
                return None
            if answer == "show":
                # ASCII JSON escapes terminal control and bidi characters, including
                # those embedded in model-controlled findings or source content.
                self._write(
                    json.dumps(
                        preview.model_dump(mode="json"), ensure_ascii=True, indent=2
                    )
                )
                continue
            if answer == "approve " + preview.sha256:
                return preview.sha256
            return None

    async def show_result(self, result: RetainedReviewResult) -> None:
        verdict = result.result.verdict
        self._write(f"Review result: {verdict.decision}")
        self._write(safe_label(verdict.rationale))
