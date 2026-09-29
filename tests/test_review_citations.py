"""Citation units preserve exact evidence without diff-marker false negatives."""

import json
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic import ValidationError

from mos_eisley.core.models import (
    Brief,
    CriticRequest,
    CriticSpec,
    Critique,
    Evidence,
    Finding,
    JudgeDecision,
    JudgeRequest,
    ReviewPolicy,
    canonical_bytes,
)
from mos_eisley.review.citations import (
    citation_bound_request,
    citation_units,
    validate_citation_catalog,
    validate_evidence,
)
from mos_eisley.review.pipeline import review


def finding(quote: str, source_unit: str | None) -> Finding:
    return Finding(
        location="review_single_operator.py:172",
        category="correctness",
        impact="high",
        claim="Cleanup leaves review authority reachable.",
        evidence=Evidence(
            source="diff",
            source_unit=source_unit,
            quote=quote,
            explanation="The cited cleanup statements are incomplete.",
        ),
    )


class ReviewCitationTests(TestCase):
    def setUp(self) -> None:
        self.diff = (
            "diff --git a/host.py b/host.py\n"
            "--- a/host.py\n"
            "+++ b/host.py\n"
            "@@ -10,2 +10,5 @@ class Host:\n"
            "     def close(self):\n"
            "+        self._credential = None\n"
            "+        self._signer = None\n"
            "+        self._authorized = None\n"
            "         self._key = None\n"
        )
        self.brief = Brief(spec="Drop review authority.", diff=self.diff)
        self.request = citation_bound_request(self.brief, "correctness")

    def unit(self, view: str) -> str:
        return next(
            unit.id for unit in self.request.citation_units if unit.view == view
        )

    def test_multiline_postimage_quote_is_exactly_supported(self) -> None:
        quote = (
            "        self._credential = None\n"
            "        self._signer = None\n"
            "        self._authorized = None\n"
        )
        validate_evidence(self.request, (finding(quote, self.unit("after")),))

    def test_raw_patch_quote_uses_content_bound_raw_unit(self) -> None:
        validate_evidence(
            self.request,
            (finding("+        self._signer = None", self.unit("raw")),),
        )

    def test_missing_invented_stale_and_wrong_view_units_fail_closed(self) -> None:
        quote = "        self._signer = None"
        stale = citation_bound_request(
            self.brief.model_copy(
                update={
                    "diff": self.diff.replace("+10,5", "+10,6") + "+changed = True\n"
                }
            ),
            "correctness",
        )
        cases = (
            finding(quote, None),
            finding(quote, "diff.after." + "0" * 64),
            finding(quote, stale.citation_units[-1].id),
            finding(quote, self.unit("before")),
        )
        for item in cases:
            with (
                self.subTest(source_unit=item.evidence.source_unit),
                self.assertRaises(ValueError),
            ):
                validate_evidence(self.request, (item,))

    def test_normalization_and_cross_hunk_splicing_are_rejected(self) -> None:
        second_diff = (
            self.diff
            + "@@ -30 +32,2 @@ class Host:\n"
            + "         pass\n"
            + "+        second = True\n"
        )
        request = citation_bound_request(
            self.brief.model_copy(update={"diff": second_diff}), "correctness"
        )
        after = tuple(
            unit.id for unit in request.citation_units if unit.view == "after"
        )
        for quote, unit in (
            ("        self._credential =  None", after[0]),
            ("        self._authorized = None\n        second = True", after[0]),
            ("        self._authorized = None\n        second = True", after[1]),
        ):
            with self.subTest(quote=quote, unit=unit), self.assertRaises(ValueError):
                validate_evidence(request, (finding(quote, unit),))

    def test_catalog_is_recomputed_and_bound_to_the_frozen_brief(self) -> None:
        changed = self.request.model_copy(
            update={"brief": self.brief.model_copy(update={"diff": self.diff + " "})}
        )
        with self.assertRaisesRegex(ValueError, "catalog"):
            validate_citation_catalog(changed)

    def test_hunk_counts_and_no_newline_marker_are_semantic(self) -> None:
        brief = Brief(
            spec="replace the value",
            diff=(
                "--- a/x\n"
                "+++ b/x\n"
                "@@ -1 +1 @@\n"
                "-old\n"
                "\\ No newline at end of file\n"
                "+new\n"
                "\\ No newline at end of file\n"
                "+trailing patch metadata\n"
            ),
        )
        request = citation_bound_request(brief, "correctness")
        after = next(unit.id for unit in request.citation_units if unit.view == "after")
        validate_evidence(request, (finding("new", after),))
        with self.assertRaises(ValueError):
            validate_evidence(
                request,
                (finding("new\n", after),),
            )
        with self.assertRaises(ValueError):
            validate_evidence(
                request,
                (finding("trailing patch metadata", after),),
            )

    def test_legacy_contract_keeps_exact_bytes_and_raw_only_semantics(self) -> None:
        legacy = CriticRequest(brief=self.brief, persona="correctness")
        expected = json.dumps(
            {
                "brief": self.brief.model_dump(mode="json"),
                "persona": "correctness",
                "schema_version": 1,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        self.assertEqual(canonical_bytes(legacy), expected)
        self.assertNotIn(
            b"source_unit",
            canonical_bytes(
                Evidence(source="diff", quote="self._key = None", explanation="exact")
            ),
        )
        validate_evidence(
            legacy,
            (finding("+        self._signer = None", None),),
        )
        with self.assertRaises(ValueError):
            validate_evidence(
                legacy,
                (
                    finding(
                        "        self._credential = None\n        self._signer = None",
                        None,
                    ),
                ),
            )

    def test_version_and_catalog_shape_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            CriticRequest(
                schema_version=2,
                brief=self.brief,
                persona="correctness",
            )
        with self.assertRaises(ValidationError):
            CriticRequest(
                brief=self.brief,
                persona="correctness",
                citation_units=citation_units(self.brief),
            )

    def test_hunk_count_is_bounded(self) -> None:
        diff = "--- a/x\n+++ b/x\n" + "".join(
            f"@@ -{index} +{index} @@\n-old\n+new\n" for index in range(1, 1026)
        )
        with self.assertRaisesRegex(ValueError, "too many"):
            citation_bound_request(Brief(spec="bounded", diff=diff), "correctness")


class CitationPipelineTests(IsolatedAsyncioTestCase):
    async def test_schema_two_supported_quote_reaches_judge(self) -> None:
        brief = Brief(
            spec="Drop review authority.",
            diff=(
                "--- a/host.py\n"
                "+++ b/host.py\n"
                "@@ -1 +1,4 @@\n"
                " def close(self):\n"
                "+    self._credential = None\n"
                "+    self._signer = None\n"
                "+    self._authorized = None\n"
            ),
        )
        critic = CriticSpec(
            id="critic", provider="fixture", model="fixture", persona="correctness"
        )

        class Reviewer:
            finding: Finding | None = None

            async def critique(
                self, critic: CriticSpec, request: CriticRequest
            ) -> Critique:
                assert critic.persona == request.persona
                unit = next(
                    item.id for item in request.citation_units if item.view == "after"
                )
                self.finding = finding(
                    "    self._credential = None\n"
                    "    self._signer = None\n"
                    "    self._authorized = None\n",
                    unit,
                )
                return Critique(findings=(self.finding,))

            async def judge(self, request: JudgeRequest) -> JudgeDecision:
                assert self.finding is not None
                return JudgeDecision(
                    upheld=(self.finding.finding_id,), rationale="Supported"
                )

        result = await review(
            brief,
            (critic,),
            Reviewer(),
            ReviewPolicy(min_critics=1, min_providers=1),
            citation_contract=2,
        )
        self.assertEqual(result.verdict.decision, "revise")
        self.assertEqual(len(result.verdict.findings), 1)
