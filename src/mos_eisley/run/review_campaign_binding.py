"""Immutable selection of one slot in an independently pinned campaign seal."""

from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest


class ReviewCampaignBinding(Contract):
    campaign_directory: Annotated[str, Field(min_length=1, max_length=4096)]
    expected_seal_sha256: Digest
    attempt_index: Annotated[int, Field(ge=0, le=2)]

    @model_validator(mode="after")
    def absolute_directory(self) -> Self:
        if not Path(self.campaign_directory).is_absolute():
            raise ValueError("campaign dispatch binding requires an absolute directory")
        return self
