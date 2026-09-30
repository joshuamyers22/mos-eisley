"""Separate write authority for an initial-child correction proposal.

Signing and previewing this grant perform no Git write or task test. A later
one-use integration broker must consume the grant before making a detached
commit and independently verify its resulting Git record.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_candidate_execution import open_private_dispatch_store
from mos_eisley.reviewer_coding_broker import (
    G4ProductionCodingChildReceipt,
    verify_production_coding_child_receipt,
)
from mos_eisley.reviewer_correction import G4CorrectionReviewPolicy
from mos_eisley.reviewer_correction_dispatch import G4CorrectionChildDispatchReceipt
from mos_eisley.reviewer_correction_integration import _preflight_tree
from mos_eisley.reviewer_initial_candidate import (
    G4InitialCandidateInputs,
    G4InitialCandidateReceipt,
)
from mos_eisley.reviewer_initial_correction import G4InitialCorrectionCycleAdmission
from mos_eisley.reviewer_initial_correction_dispatch import (
    verify_initial_correction_child_dispatch_receipt,
)
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    RelativePath,
    SourceRevision,
    _git,
    _git_text,
    verify_provenance_signature,
)

_APPROVAL_DOMAIN = b"mos-eisley/g4-initial-correction-integration-approval/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("initial correction integration needs explicit UTC")
    return value


class G4InitialCorrectionIntegrationApproval(Contract):
    """Exact creator authority to write one detached correction worktree."""

    schema_version: Literal[1] = 1
    kind: Literal["g4_initial_correction_integration_approval"] = (
        "g4_initial_correction_integration_approval"
    )
    integration_id: Identifier
    policy_sha256: Digest
    admission_sha256: Digest
    child_dispatch_receipt_sha256: Digest
    production_receipt_sha256: Digest
    source_revision: SourceRevision
    source_root_sha256: Digest
    integration_store_sha256: Digest
    owned_paths: Annotated[tuple[RelativePath, ...], Field(min_length=1, max_length=64)]
    issued_at: datetime
    expires_at: datetime
    isolated_worktree_write_authorized: Literal[True] = True
    checked_out_worktree_write_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    final_test_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("initial correction integration window is invalid")
        if self.owned_paths != tuple(sorted(set(self.owned_paths))):
            raise ValueError("initial correction integration paths must be unique")
        return self


class SignedG4InitialCorrectionIntegrationApproval(Contract):
    approval: G4InitialCorrectionIntegrationApproval
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_initial_correction_integration_approval(
    approval: G4InitialCorrectionIntegrationApproval,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4InitialCorrectionIntegrationApproval:
    """Sign externally; the private creator key never enters the verifier."""
    return SignedG4InitialCorrectionIntegrationApproval(
        approval=approval,
        signature=G4ArtifactSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(_APPROVAL_DOMAIN + canonical_bytes(approval))
            ).decode("ascii"),
        ),
    )


def verify_initial_correction_integration_approval(
    signed: SignedG4InitialCorrectionIntegrationApproval,
    *,
    admission: G4InitialCorrectionCycleAdmission,
    dispatch: G4CorrectionChildDispatchReceipt,
    production: G4ProductionCodingChildReceipt,
    first: G4InitialCandidateReceipt,
    reproduction: G4InitialCandidateReceipt,
    first_inputs: G4InitialCandidateInputs,
    reproduction_inputs: G4InitialCandidateInputs,
    review_policy: G4CorrectionReviewPolicy,
    correction_store: Path,
    child_dispatch_store: Path,
    production_store: Path,
    integration_store: Path,
    now: datetime | None = None,
) -> None:
    """Replay exact authority and current clean source without spending it."""
    current = _utc(now if now is not None else datetime.now(UTC))
    source_root = first_inputs.integrated_root.resolve(strict=True)
    original_root = first_inputs.original_root.resolve(strict=True)
    fd = open_private_dispatch_store(integration_store)
    try:
        store = integration_store.resolve(strict=True)
    finally:
        os.close(fd)
    if (
        first_inputs.integrated_root.is_symlink()
        or first_inputs.original_root.is_symlink()
        or source_root == original_root
        or any(
            path.resolve().is_relative_to(root)
            for root in (source_root, original_root)
            for path in (
                correction_store,
                child_dispatch_store,
                production_store,
                store,
            )
        )
        or source_root.is_relative_to(store)
        or original_root.is_relative_to(store)
    ):
        raise ValueError("initial correction integration state overlaps Git")
    verify_initial_correction_child_dispatch_receipt(
        dispatch,
        admission=admission,
        first=first,
        reproduction=reproduction,
        first_inputs=first_inputs,
        reproduction_inputs=reproduction_inputs,
        review_policy=review_policy,
        correction_store=correction_store,
        child_dispatch_store=child_dispatch_store,
        container=first_inputs.container,
    )
    verify_production_coding_child_receipt(
        production, dispatch, first_inputs.policy, first_inputs.ledger, production_store
    )
    order = signed.approval
    cycle = admission.approval.approval
    if (
        order.policy_sha256 != first_inputs.policy.policy_sha256
        or order.admission_sha256 != admission.admission_sha256
        or order.child_dispatch_receipt_sha256 != digest(canonical_bytes(dispatch))
        or order.production_receipt_sha256 != production.receipt_sha256
        or order.source_revision != admission.source_revision
        or order.source_root_sha256 != digest(str(source_root).encode("utf-8"))
        or order.integration_store_sha256 != digest(str(store).encode("utf-8"))
        or order.owned_paths != dispatch.execution.changed_paths
        or dispatch.execution.unresolved_issue_count != 0
        or not dispatch.dispatched_at <= order.issued_at <= current < order.expires_at
        or order.expires_at > cycle.expires_at
        or order.expires_at > cycle.task_budget.deadline
        or order.expires_at > first_inputs.policy.valid_until
        or order.issued_at < first_inputs.policy.valid_from
    ):
        raise ValueError("initial correction integration differs from signed task")
    verify_provenance_signature(
        order,
        signed.signature,
        first_inputs.policy,
        "creator",
        _APPROVAL_DOMAIN,
    )
    if _git_text(first_inputs.git_executable, source_root, ["rev-parse", "HEAD"]) != (
        order.source_revision
    ) or _git(
        first_inputs.git_executable,
        source_root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ):
        raise ValueError("initial correction integration source Git changed")
    _preflight_tree(first_inputs.git_executable, source_root, order.source_revision)
