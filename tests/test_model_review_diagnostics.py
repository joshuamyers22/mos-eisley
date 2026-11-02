"""Strict artifact gates expose useful reasons without native output or keys."""

import json
import unittest

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from mos_eisley.conversation_live_coding import ModelReview, decode_model
from mos_eisley.core.models import digest
from mos_eisley.model_review_diagnostics import (
    MAX_ISSUES,
    MAX_REVIEW_BYTES,
    ModelReviewArtifactError,
    ModelReviewReceipt,
    validate_model_review,
)

SECRET = "private-native-/tmp/fixture-token"
SUBJECT = digest(b"synthetic reviewed artifact")


def artifact(**updates: object) -> str:
    return json.dumps(
        {"subject_sha256": SUBJECT, "decision": "accept", "findings": [], **updates}
    )


class ModelReviewDiagnosticTests(unittest.TestCase):
    def test_advertised_schema_matches_runtime_decision_findings_rules(self) -> None:
        validator = Draft202012Validator(ModelReview.model_json_schema())
        for decision in ("accept", "revise", "approve"):
            for findings in ([], ["Concrete defect"], ["x"] * 17, None):
                for include in (True, False):
                    value = json.loads(artifact(decision=decision, findings=findings))
                    if not include:
                        del value["findings"]
                    with self.subTest(
                        decision=decision, findings=findings, include=include
                    ):
                        try:
                            ModelReview.model_validate_json(json.dumps(value))
                            runtime_valid = True
                        except ValidationError:
                            runtime_valid = False
                        # jsonschema's overloaded third-party stub is partial.
                        advertised = validator.is_valid(value)  # pyright: ignore[reportUnknownMemberType]
                        self.assertEqual(advertised, runtime_valid)

    def failure(self, text: str, expected: str | None = None) -> ModelReviewReceipt:
        with self.assertRaises(ModelReviewArtifactError) as raised:
            validate_model_review(ModelReview, text, expected_subject=expected)
        receipt = raised.exception.receipt
        self.assertNotIn(SECRET, str(raised.exception) + receipt.model_dump_json())
        self.assertLess(len(receipt.model_dump_json().encode()), 4096)
        self.assertEqual(receipt.status, "invalid")
        return receipt

    def test_valid_review_and_revision_keep_strict_types_and_subject(self) -> None:
        for decision, findings in (
            ("accept", []),
            ("revise", ["Concrete synthetic defect."]),
        ):
            text = artifact(decision=decision, findings=findings)
            model, receipt = validate_model_review(
                ModelReview, text, expected_subject=SUBJECT
            )
            self.assertEqual(model, decode_model(ModelReview, text))
            self.assertEqual((receipt.status, receipt.stage), ("valid", "complete"))
            self.assertTrue(receipt.subject_matches)
            self.assertEqual(receipt.artifact_sha256, digest(text.encode()))
            self.assertEqual(receipt.issues, ())

    def test_invalid_json_fences_duplicates_and_root_are_not_repaired(self) -> None:
        for text, code in (
            ("```json\n" + artifact() + "\n```", "invalid_json"),
            ('{"decision":', "invalid_json"),
            ('{"decision":"revise","decision":"accept"}', "duplicate_keys"),
            ('{"findings":[{"x":1,"x":2}]}', "duplicate_keys"),
            (json.dumps([SECRET]), "wrong_root"),
            ("null", "wrong_root"),
        ):
            with self.subTest(code=code):
                receipt = self.failure(text)
                self.assertEqual(receipt.issues[0].code, code)
                with self.assertRaises(ValueError):
                    decode_model(ModelReview, text)
        self.assertEqual(self.failure("```json\n{}\n```").json_prefix, "markdown_fence")

    def test_field_type_value_and_decision_consistency_reasons_are_fixed(self) -> None:
        for text, code, field in (
            ('{"decision":"accept"}', "missing_field", "subject_sha256"),
            (artifact(subject_sha256=SECRET), "invalid_digest", "subject_sha256"),
            (artifact(decision=SECRET), "invalid_decision", "decision"),
            (artifact(decision="approve"), "invalid_decision", "decision"),
            (artifact(findings=SECRET), "wrong_type", "findings"),
            (artifact(findings=[{"detail": SECRET}]), "wrong_type", "findings"),
            (artifact(findings=[SECRET]), "decision_findings_conflict", "root"),
            (artifact(decision="revise"), "decision_findings_conflict", "root"),
            (
                artifact(decision="revise", findings=["x"] * 17),
                "too_many_findings",
                "findings",
            ),
        ):
            with self.subTest(code=code, field=field):
                receipt = self.failure(text)
                self.assertEqual(
                    (receipt.issues[0].code, receipt.issues[0].field), (code, field)
                )
        value = self.failure(artifact(decision="approve"))
        self.assertEqual(value.decision_token, "approve")
        self.assertEqual(
            self.failure(artifact(decision=SECRET)).decision_token, "other"
        )

    def test_subject_binding_is_part_of_same_gate(self) -> None:
        receipt = self.failure(artifact(), digest(b"different artifact"))
        self.assertEqual(receipt.stage, "binding")
        self.assertEqual(receipt.issues[0].code, "subject_mismatch")
        self.assertEqual(receipt.issues[0].field, "subject_sha256")
        self.assertFalse(receipt.subject_matches)

    def test_arbitrary_extra_keys_and_validation_context_never_escape(self) -> None:
        text = artifact(**{f"{SECRET}{i}": SECRET for i in range(100)})
        value = self.failure(text)
        self.assertEqual(value.error_count, 100)
        self.assertEqual(value.extra_fields, 100)
        self.assertEqual(len(value.issues), MAX_ISSUES)
        self.assertTrue(value.issues_truncated)
        self.assertTrue(all(i.field == "unrecognized" for i in value.issues))
        self.assertTrue(all(i.code == "extra_field" for i in value.issues))

    def test_input_and_encoding_limits_refuse_before_schema(self) -> None:
        for text, code in (
            ("x" * (MAX_REVIEW_BYTES + 1), "input_limit"),
            ("☃" * 32000, "input_limit"),
            ("\ud800", "invalid_encoding"),
        ):
            with self.subTest(code=code):
                value = self.failure(text)
                self.assertEqual((value.stage, value.issues[0].code), ("input", code))

    def test_receipt_schema_refuses_content_and_invalid_numeric_fields(self) -> None:
        _, receipt = validate_model_review(ModelReview, artifact())
        for key, replacement in (
            ("text", SECRET),
            ("decision_token", SECRET),
            ("error_count", True),
            ("error_count", 1_000_001),
        ):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                ModelReviewReceipt.model_validate(
                    {**receipt.model_dump(), key: replacement}
                )


if __name__ == "__main__":
    unittest.main()
