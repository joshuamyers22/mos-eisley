"""Retained skill bytes must exactly match current authenticated promotion evidence."""

import io
import json
import stat
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.core.skills import PromptAsset, SkillPackageArchive
from mos_eisley.evaluation.skill_promotion import AuthenticatedSkillPromotion
from mos_eisley.run.skill_release import (
    SkillReleaseEvidence,
    bind_skill_release_evidence,
    verify_skill_release_evidence,
)
from mos_eisley.run.skills import discover_skills
from mos_eisley.run.store import private_write
from tests import test_skill_comparison as comparison_module
from tests import test_skill_promotion as promotion_module
from tests.test_skills import write_skill


class SkillReleaseEvidenceTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        skill_root = self.root / "skills"
        write_skill(
            skill_root,
            "adversarial-reviewer",
            "Review this change adversarially.",
            sidecar="version: 1.0.0\nkind: persona\n",
        )
        catalog = discover_skills(project_roots=(skill_root,))
        identity = catalog.descriptors[0].identity
        self.archive = catalog.archive(identity.qualified_reference, allow_project=True)

        baseline, template = comparison_module._routes()  # pyright: ignore[reportPrivateUsage]
        candidate = template.model_copy(
            update={
                "prompt": PromptAsset(
                    mode="skill",
                    instructions="Review this change adversarially.",
                    skill=identity,
                )
            }
        )
        with patch.object(
            comparison_module, "_routes", return_value=(baseline, candidate)
        ):
            self.promotion = promotion_module.SkillPromotionTests()
            self.promotion.setUp()
        self.receipt = self.promotion.authenticate()
        self.checked_at = self.promotion.issued_at + timedelta(minutes=5)

    def bind(
        self,
        *,
        archive: SkillPackageArchive | None = None,
        receipt: AuthenticatedSkillPromotion | None = None,
        now: datetime | None = None,
    ) -> SkillReleaseEvidence:
        fixture = self.promotion
        return bind_skill_release_evidence(
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            receipt or self.receipt,
            fixture.authority_policy,
            archive or self.archive,
            now or self.checked_at,
        )

    def test_binds_exact_archive_to_current_recomputed_promotion(self) -> None:
        evidence = self.bind()
        self.assertEqual(evidence.archive_sha256, self.archive.archive_sha256)
        self.assertEqual(
            evidence.promotion_receipt_sha256,
            self.receipt.promotion_receipt_sha256,
        )
        self.assertEqual(evidence.candidate_skill, self.archive.descriptor.identity)
        self.assertTrue(evidence.package_retained)
        self.assertTrue(evidence.promotion_ready)
        self.assertFalse(evidence.installation_authorized)
        self.assertFalse(evidence.activation_authorized)
        self.assertFalse(evidence.configuration_mutation_authorized)
        self.assertEqual(len(evidence.release_evidence_sha256), 64)

        fixture = self.promotion
        verify_skill_release_evidence(
            fixture.source.dataset,
            fixture.source.plan,
            fixture.calibration,
            fixture.holdout,
            fixture.source.sealed,
            fixture.source.holdout_claim,
            fixture.calibration_report,
            fixture.holdout_report,
            self.receipt,
            fixture.authority_policy,
            self.archive,
            evidence,
            self.checked_at,
        )

    def test_mismatched_package_and_expired_receipt_fail_closed(self) -> None:
        other_root = self.root / "other"
        write_skill(
            other_root,
            "different-reviewer",
            "Review this change adversarially.",
            sidecar="version: 1.0.0\nkind: persona\n",
        )
        catalog = discover_skills(project_roots=(other_root,))
        identity = catalog.descriptors[0].identity
        other = catalog.archive(identity.qualified_reference, allow_project=True)
        with self.assertRaisesRegex(ValueError, "differs from promoted"):
            self.bind(archive=other)
        with self.assertRaisesRegex(ValueError, "not current"):
            self.bind(now=self.receipt.valid_until)

    def test_tampering_and_deployment_authority_fail_closed(self) -> None:
        evidence = self.bind()
        value = evidence.model_dump(mode="json")
        value["installation_authorized"] = True
        with self.assertRaises(ValidationError):
            SkillReleaseEvidence.model_validate_json(json.dumps(value))

        changed = evidence.model_copy(update={"archive_sha256": "f" * 64})
        fixture = self.promotion
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            verify_skill_release_evidence(
                fixture.source.dataset,
                fixture.source.plan,
                fixture.calibration,
                fixture.holdout,
                fixture.source.sealed,
                fixture.source.holdout_claim,
                fixture.calibration_report,
                fixture.holdout_report,
                self.receipt,
                fixture.authority_policy,
                self.archive,
                changed,
                self.checked_at,
            )
        with self.assertRaisesRegex(ValueError, "outside its validity window"):
            evidence.check_current(evidence.valid_until)

    def test_cli_reverifies_full_lineage_and_writes_private_evidence(self) -> None:
        fixture = self.promotion
        values: dict[str, Contract] = {
            "dataset": fixture.source.dataset,
            "plan": fixture.source.plan,
            "sealed": fixture.source.sealed,
            "claim": fixture.source.holdout_claim,
            "calibration_report": fixture.calibration_report,
            "holdout_report": fixture.holdout_report,
            "receipt": self.receipt,
            "authority_policy": fixture.authority_policy,
            "archive": self.archive,
        }
        lineage_names = (
            "batch",
            "mapping",
            "raw",
            "grading",
            "dual",
            "grading_policy",
            "resolution_policy",
            "observations",
        )
        for prefix, lineage in (
            ("calibration", fixture.calibration),
            ("holdout", fixture.holdout),
        ):
            values.update(
                {
                    f"{prefix}_{name}": value
                    for name, value in zip(lineage_names, lineage, strict=True)
                }
            )
        paths = {name: self.root / f"{name}.json" for name in values}
        for name, value in values.items():
            private_write(paths[name], canonical_bytes(value))

        arguments = [
            "eval-bind-skill-release-evidence",
            "--dataset",
            str(paths["dataset"]),
            "--plan",
            str(paths["plan"]),
            "--sealed-comparison",
            str(paths["sealed"]),
            "--holdout-use-claim",
            str(paths["claim"]),
            "--calibration-report",
            str(paths["calibration_report"]),
            "--holdout-report",
            str(paths["holdout_report"]),
            "--promotion-receipt",
            str(paths["receipt"]),
            "--authority-policy",
            str(paths["authority_policy"]),
            "--archive",
            str(paths["archive"]),
        ]
        cli_names = (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        )
        artifact_names = (
            "batch",
            "mapping",
            "raw",
            "grading",
            "dual",
            "observations",
            "grading_policy",
            "resolution_policy",
        )
        for prefix in ("calibration", "holdout"):
            for cli_name, artifact_name in zip(cli_names, artifact_names, strict=True):
                arguments.extend(
                    (
                        f"--{prefix}-{cli_name}",
                        str(paths[f"{prefix}_{artifact_name}"]),
                    )
                )
        output = self.root / "release-evidence.json"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main([*arguments, "--output", str(output)]), 0)
        event = json.loads(stdout.getvalue())
        evidence = SkillReleaseEvidence.model_validate_json(output.read_bytes())
        self.assertEqual(event["type"], "evaluation.skill_release_evidence.bound")
        self.assertEqual(
            event["release_evidence_sha256"], evidence.release_evidence_sha256
        )
        self.assertFalse(event["installation_authorized"])
        self.assertFalse(event["activation_authorized"])
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
