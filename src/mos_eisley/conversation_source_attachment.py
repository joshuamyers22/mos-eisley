"""Preserve the distinct frozen workspace and Git-review attachment formats."""

from mos_eisley.conversation_diff import (
    DiffAttachment as ReviewDiffAttachment,
)
from mos_eisley.conversation_diff import attachment_suffix
from mos_eisley.conversation_diff_attachment import (
    DiffAttachment,
    DiffAttachmentError,
)
from mos_eisley.conversation_diff_attachment import (
    attachment_payload as workspace_payload,
)
from mos_eisley.core.models import digest

type SourceAttachment = DiffAttachment | ReviewDiffAttachment


def attachment_payload(attachments: tuple[SourceAttachment, ...]) -> str:
    if not attachments:
        return ""
    if all(isinstance(item, DiffAttachment) for item in attachments):
        return workspace_payload(
            tuple(item for item in attachments if isinstance(item, DiffAttachment))
        )
    if all(isinstance(item, ReviewDiffAttachment) for item in attachments):
        if len(attachments) > 4:
            raise DiffAttachmentError(
                "At most four Git-review excerpts can be attached."
            )
        return attachment_suffix(
            tuple(
                item for item in attachments if isinstance(item, ReviewDiffAttachment)
            )
        )
    raise DiffAttachmentError("Send each attachment format in a separate message.")


def attachment_fingerprint(attachments: tuple[SourceAttachment, ...]) -> str | None:
    return digest(attachment_payload(attachments).encode()) if attachments else None
