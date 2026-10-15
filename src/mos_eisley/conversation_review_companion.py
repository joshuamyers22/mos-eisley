"""Read-only review inspection. This component cannot approve or dispatch work."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import TextArea

from mos_eisley.conversation_presentation import fit_label
from mos_eisley.conversation_review import ConversationLiveReviewPacket, ReviewPacket
from mos_eisley.terminal_text import safe_label


@dataclass(frozen=True)
class ReviewInspection:
    action: str
    scope: str
    reason: str
    status: str
    details: str
    family: str = ""


def packet_inspection(packet: ReviewPacket) -> ReviewInspection:
    live = isinstance(packet, ConversationLiveReviewPacket)
    identities = ["Brief SHA-256: " + packet.brief.brief_id]
    if isinstance(packet, ConversationLiveReviewPacket):
        identities.extend(
            name + ": " + getattr(packet, name)
            for name in (
                "prepared_sha256",
                "configuration_sha256",
                "campaign_seal_sha256",
                "campaign_evidence_sha256",
                "manifest_sha256",
            )
        )
    return ReviewInspection(
        action="Inspect selected live review" if live else "Inspect recorded review",
        scope=(
            f"{packet.git_scope.selection.kind} • "
            f"{len(packet.git_scope.files)} files • {packet.git_scope.workspace}"
            if packet.git_scope is not None
            else "Frozen brief: specification, diff and constraints"
        ),
        reason=(
            "Live dispatch needs the existing signed launch and phase approvals."
            if live
            else "Only the explicitly selected packet can supply this recorded review."
        ),
        status="Selection only; no approval granted",
        details=(
            "\n".join(identities)
            + "\n\nSelected packet (exact identities and complete content)\n"
            + json.dumps(packet.model_dump(mode="json"), ensure_ascii=True, indent=2)
            + "\n\nUse the existing /review command to request this review. "
            "This inspector cannot submit, approve or retry it."
        ),
    )


class ReviewCompanion:
    def __init__(self, packet: ReviewPacket | None = None) -> None:
        self.inspection = None if packet is None else packet_inspection(packet)
        self.visible = False
        self.details = TextArea(
            read_only=True,
            focusable=False,
            scrollbar=True,
            wrap_lines=True,
            height=Dimension(min=1, max=7),
        )
        self.details.window.dont_extend_height = Condition(lambda: True)
        self.sync()

    def sync(self) -> None:
        inspection = self.inspection
        text = (
            "No review packet or approval preview is selected.\n"
            "Select a review packet at launch, or request a memory-change preview."
            if inspection is None
            else (
                inspection.details
                + "\n\nContext\nAction: "
                + safe_label(inspection.action)
                + "\nScope: "
                + safe_label(inspection.scope)
                + "\nReason: "
                + safe_label(inspection.reason)
                + "\nStatus: "
                + safe_label(inspection.status)
            )
        )
        if text != self.details.text:
            self.details.buffer.set_document(Document(text, 0), bypass_readonly=True)

    def toggle(self) -> None:
        self.visible = not self.visible

    def close(self) -> None:
        # Closing the view is not a backend cancellation or approval.
        self.visible = False

    def receive(self, event: dict[str, object]) -> None:
        kind = str(event.get("type", ""))
        families = {
            "conversation.memory.forget.preview": (
                "forget",
                "Remove exact memory text",
            ),
            "conversation.memory.replace.preview": (
                "replace",
                "Replace exact memory text",
            ),
            "conversation.memory.proposal.preview": (
                "proposal",
                "Apply selected memory proposal",
            ),
        }
        if kind in families:
            family, action = families[kind]
            token = event.get("preview_sha256")
            if (
                not isinstance(token, str)
                or re.fullmatch(r"[0-9a-f]{64}", token) is None
            ):
                # Do not synthesize a missing approval identity.
                self.inspection = ReviewInspection(
                    action,
                    "Unavailable",
                    "Request a fresh preview with its exact hash.",
                    "Incomplete receipt; no approval available",
                    "No valid preview hash.",
                )
            else:
                self.inspection = ReviewInspection(
                    action=action,
                    scope=safe_label(str(event.get("scope", "unspecified")))
                    + " memory • "
                    + safe_label(str(event.get("path", "unspecified"))),
                    reason=(
                        "Changes saved memory; inspect the exact target "
                        "and resulting text."
                    ),
                    status="Not applied • verify before applying",
                    details=(
                        "Exact preview SHA-256\n"
                        + token
                        + f"\n\nApply explicitly: /memory apply-{family} {token}"
                        + f"\nDiscard explicitly: /memory discard-{family}"
                        + "\nClosing this view does not discard the pending preview."
                        + "\n\n"
                        + "Preview receipt (source text is untrusted data)\n"
                        + json.dumps(event, ensure_ascii=True, indent=2)
                    ),
                    family=family,
                )
            self.visible = True
        elif kind == "conversation.review_scope":
            self.inspection = ReviewInspection(
                "Inspect frozen Git review scope",
                safe_label(str(event.get("workspace", "Selected workspace"))),
                "Check the selected files and comparison before requesting review.",
                "Scope receipt only; no acceptance or posting authority",
                json.dumps(event, ensure_ascii=True, indent=2),
            )
            self.visible = True
        elif self.inspection is not None and self.inspection.family:
            family = self.inspection.family
            if kind in {
                f"conversation.memory.{family}.saved",
                f"conversation.memory.{family}.discarded",
            }:
                # Remove apply instructions after completion or discard.
                self.inspection = replace(
                    self.inspection,
                    status="Saved receipt" if kind.endswith(".saved") else "Discarded",
                    details=json.dumps(event, ensure_ascii=True, indent=2),
                    family="",
                )
            elif kind in {"conversation.error", "conversation.unavailable"} or (
                kind.startswith("conversation.memory.")
                and not kind.endswith(".preview")
            ):
                self.inspection = replace(
                    self.inspection,
                    status="Historical preview; recheck required",
                    reason=(
                        "State may have changed. Inspect memory and "
                        "request a fresh preview."
                    ),
                )
        self.sync()

    def summary(self, width: int) -> str:
        item = self.inspection
        if item is None:
            return "Review / approval inspector\nNo selected request\nInspection only"
        return "\n".join(
            fit_label(label, width)
            for label in (
                "Action: " + item.action,
                "Scope: " + item.scope,
                "Reason: " + item.reason,
            )
        )

    def heading(self, width: int) -> str:
        status = "No selection" if self.inspection is None else self.inspection.status
        return fit_label("Review / approval • " + status, width)

    def panel(self, width: Callable[[], int]) -> ConditionalContainer:
        return ConditionalContainer(
            HSplit(
                [
                    Window(
                        FormattedTextControl(lambda: self.heading(width())),
                        height=1,
                        style="class:header",
                    ),
                    Window(
                        FormattedTextControl(lambda: self.summary(width())), height=3
                    ),
                    self.details,
                    Window(
                        FormattedTextControl(
                            "Ctrl-O / Ctrl-G close • Alt-PageUp/Down details"
                        ),
                        height=1,
                        style="class:muted",
                    ),
                ]
            ),
            filter=Condition(lambda: self.visible),
        )
