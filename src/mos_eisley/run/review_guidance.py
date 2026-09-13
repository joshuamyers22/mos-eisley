"""Explicit current guidance at short local broker consumption boundaries."""

from pathlib import Path

from pydantic import JsonValue

from mos_eisley.core.models import Brief, canonical_bytes
from mos_eisley.project_guidance_review import (
    PreparedGuidanceReview,
    decode_prepared_review,
    verify_current_review,
)
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore
from mos_eisley.providers.openai_spend import CountedTransport


class ReviewGuidanceAdmission:
    """Host-selected policy and store; retained paths never select these inputs."""

    def __init__(
        self,
        store: RoleContextAdmissionStore,
        workspace: Path,
        prepared: PreparedGuidanceReview,
        policy_path: Path,
        expected_policy_sha256: str,
    ) -> None:
        self._prepared = canonical_bytes(prepared)
        self._store = store
        self._workspace = workspace.absolute()
        self._policy_path = policy_path.absolute()
        self._policy_sha256 = expected_policy_sha256
        self.check()

    @property
    def prepared(self) -> PreparedGuidanceReview:
        return decode_prepared_review(self._prepared)

    def check_brief(self, brief: Brief) -> None:
        if brief != self.prepared.brief:
            raise ValueError("Review request differs from its selected guided brief.")
        self.check()

    def check(self) -> None:
        """Moment-of-use check; all guidance locks release before returning."""
        try:
            verify_current_review(
                self._store,
                self._workspace,
                self.prepared,
                self._policy_path,
                self._policy_sha256,
            )
        except (OSError, ValueError):
            raise ValueError("Review guidance changed or is unavailable.") from None


class GuidanceCheckedTransport:
    """Recheck around awaits without holding a guidance lock over provider work."""

    def __init__(
        self, transport: CountedTransport, admission: ReviewGuidanceAdmission
    ) -> None:
        self._transport = transport
        self._admission = admission

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        self._admission.check()
        count = await self._transport.count_input_tokens(payload)
        self._admission.check()
        return count

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self._admission.check()
        response = await self._transport.create_response(payload)
        self._admission.check()
        return response
