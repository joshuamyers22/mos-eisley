"""Ephemeral, explicit policy selection for guided terminal reviews."""

from collections.abc import Callable
from pathlib import Path

from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.project_guidance_review import verify_current_review
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore


def review_guidance_validator(
    workspace: Path,
    storage: Path,
    policy_path: Path | None,
    expected_policy_sha256: str | None,
) -> Callable[[ConversationReviewPacket], None] | None:
    if (policy_path is None) != (expected_policy_sha256 is None):
        raise ValueError(
            "Review guidance policy and its expected hash must be selected together."
        )
    if policy_path is None or expected_policy_sha256 is None:
        return None
    store = RoleContextAdmissionStore(storage)

    def validate(packet: ConversationReviewPacket) -> None:
        if packet.guidance_review is None:
            return
        try:
            verify_current_review(
                store,
                workspace,
                packet.guidance_review,
                policy_path,
                expected_policy_sha256,
            )
        except (OSError, ValueError):
            raise ValueError(
                "Review guidance changed or is unavailable; select current inputs."
            ) from None

    return validate
