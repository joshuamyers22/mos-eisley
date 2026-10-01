"""Final authority must identify the signed metadata descendant."""

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import Contract, canonical_bytes, digest
from mos_eisley.reviewer_final_suites import (
    G4FinalWholeSuiteApproval,
    sign_final_whole_suite_approval,
)
from mos_eisley.reviewer_initial_final import (
    G4InitialFinalInputs,
    preflight_initial_final,
)
from mos_eisley.reviewer_provenance import G4ProvenanceTrustPolicy, provenance_signer
from mos_eisley.reviewer_test_execution import ReviewerTestExecutionRequest


class MetadataFinalAuthorityTests(unittest.TestCase):
    def test_original_commit_or_provenance_cannot_authorize_descendant(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            key = Ed25519PrivateKey.generate()
            human = provenance_signer("owner", key.public_key())
            now = datetime.now(UTC)
            policy = G4ProvenanceTrustPolicy(
                schema_version=2,
                policy_id="final",
                creators=(human,),
                reviewers=(human,),
                vcs_brokers=(human,),
                children=(
                    provenance_signer(
                        "child", Ed25519PrivateKey.generate().public_key()
                    ),
                ),
                operator_mode="single_operator",
                valid_from=now - timedelta(hours=1),
                valid_until=now + timedelta(hours=2),
            )
            image = "sha256:" + "a" * 64
            binding_hash = digest(b"binding")
            creator_request = ReviewerTestExecutionRequest(
                execution_id="creator",
                binding_record_sha256=binding_hash,
                container_image_id=image,
                role="candidate",
            )
            reviewer_request = creator_request.model_copy(
                update={"execution_id": "reviewer"}
            )
            original = SimpleNamespace(
                record=SimpleNamespace(integrated_revision="a" * 40)
            )
            metadata = SimpleNamespace(
                record=SimpleNamespace(revision="b" * 40),
                artifact_sha256=digest(b"metadata"),
            )
            creator_package = SimpleNamespace(
                frozen_package_sha256=digest(b"creator package")
            )
            chain = SimpleNamespace(
                integrated_root=root / "implementation",
                candidate_store=root / "candidate",
                package_path=root / "reviewer.json",
                policy=policy,
                signed_integration=original,
                signed_metadata=metadata,
                creator=SimpleNamespace(
                    approval=SimpleNamespace(
                        creator_test_suite_sha256=digest(b"creator tests")
                    )
                ),
                package=SimpleNamespace(
                    frozen_package_sha256=digest(b"reviewer package")
                ),
                binding=SimpleNamespace(binding_record_sha256=binding_hash),
                container=SimpleNamespace(image_id=image),
            )
            chain.integrated_root.mkdir()
            candidate = SimpleNamespace(
                candidate_tests_passed=True,
                ran_at=now - timedelta(minutes=1),
                receipt_sha256=digest(b"candidate"),
            )
            inputs = cast(
                G4InitialFinalInputs,
                SimpleNamespace(
                    chain=chain,
                    candidate=candidate,
                    creator_package=creator_package,
                    creator_package_path=root / "creator.json",
                    creator_request=creator_request,
                    reviewer_request=reviewer_request,
                    final_store=root / "final",
                ),
            )
            grant = G4FinalWholeSuiteApproval(
                suite_id="g4-q3-real-initial-final-fixture",
                policy_sha256=policy.policy_sha256,
                provenance_sha256=metadata.artifact_sha256,
                candidate_receipt_sha256=candidate.receipt_sha256,
                source_revision="b" * 40,
                creator_test_suite_sha256=chain.creator.approval.creator_test_suite_sha256,
                creator_package_sha256=creator_package.frozen_package_sha256,
                reviewer_package_sha256=chain.package.frozen_package_sha256,
                reviewer_binding_sha256=binding_hash,
                creator_request_sha256=creator_request.request_sha256,
                reviewer_request_sha256=reviewer_request.request_sha256,
                container_image_id=image,
                issued_at=now,
                expires_at=now + timedelta(hours=1),
            )

            def exact_bytes(value: object) -> bytes:
                return (
                    b"original"
                    if value is original
                    else canonical_bytes(cast(Contract, value))
                )

            prefix = "mos_eisley.reviewer_initial_final."
            with (
                patch(prefix + "verify_initial_candidate_receipt"),
                patch(prefix + "canonical_bytes", side_effect=exact_bytes),
                patch(prefix + "read_bounded", return_value=b"package"),
                patch(
                    prefix + "decode_frozen_reviewer_test_package",
                    return_value=creator_package,
                ),
                patch(prefix + "_verify_creator_package"),
                patch(prefix + "build_isolated_creator_test_job"),
                patch(prefix + "build_isolated_reviewer_test_job"),
            ):
                preflight_initial_final(
                    sign_final_whole_suite_approval(grant, "owner", key),
                    inputs,
                    now=now,
                )
                for changes in (
                    {"source_revision": "a" * 40},
                    {"provenance_sha256": digest(b"original")},
                ):
                    with self.assertRaisesRegex(
                        ValueError, "exact initial-child inputs"
                    ):
                        preflight_initial_final(
                            sign_final_whole_suite_approval(
                                grant.model_copy(update=changes), "owner", key
                            ),
                            inputs,
                            now=now,
                        )
                chain.signed_metadata = None
                legacy = grant.model_copy(
                    update={
                        "source_revision": "a" * 40,
                        "provenance_sha256": digest(b"original"),
                    }
                )
                preflight_initial_final(
                    sign_final_whole_suite_approval(legacy, "owner", key),
                    inputs,
                    now=now,
                )
