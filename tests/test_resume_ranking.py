"""Ranked discovery is bounded metadata processing, never selection authority."""

import itertools
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_name import SessionSelectionError
from mos_eisley.conversation_resume_rank import (
    ResumeMatch,
    bounded_edit_distance,
    rank_sessions,
)
from mos_eisley.run.conversation_names import named_sessions, resume_catalog
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore, ConversationSummary


def summary(index: int, name: str | None, time: int = 0) -> ConversationSummary:
    return ConversationSummary(
        session_id=f"{index:032x}",
        session_name=name,
        snapshot_sha256="0" * 64,
        revision=0,
        modified_ns=time,
        messages=0,
        completed=0,
        pending=0,
        active=False,
        snapshot_bytes=1,
        snapshot_max_bytes=100000,
    )


class ResumeRankingTests(TestCase):
    def test_match_tiers_outrank_recency_and_report_basis(self) -> None:
        rows = (
            summary(1, "Parser", 1),
            summary(2, "Parser cleanup", 2),
            summary(3, "Cleanup parser", 3),
            summary(4, "Parsar", 999),
            summary(5, None, 1000),
        )
        matches = rank_sessions(rows[::-1], "parser")
        self.assertEqual(
            [m.summary.session_id for m in matches], [r.session_id for r in rows[:4]]
        )
        self.assertEqual(
            [m.basis for m in matches],
            ["exact_name", "name_prefix", "name_words", "fuzzy_name"],
        )
        self.assertEqual(matches[-1].label, "Similar name (1 edit)")
        words = rank_sessions(rows, "parser cleanup")
        self.assertEqual([m.basis for m in words[:2]], ["exact_name", "name_words"])
        self.assertEqual(rank_sessions(rows, rows[4].session_id)[0].basis, "exact_id")
        self.assertEqual(rank_sessions((rows[4],), "0000")[0].basis, "id_fragment")

    def test_unicode_duplicates_unnamed_and_restart_order(self) -> None:
        rows = (
            summary(3, "Straße", 9),
            summary(2, "STRASSE", 9),
            summary(1, "Café", 10),
            summary(4, None, 11),
        )
        for ordering in itertools.permutations(rows):
            self.assertEqual(
                [m.summary.session_id for m in rank_sessions(ordering, " strasse ")],
                [rows[1].session_id, rows[0].session_id],
            )
            self.assertEqual(rank_sessions(ordering, "CAFE\u0301")[0].summary, rows[2])
            self.assertEqual(
                [m.summary.session_id for m in rank_sessions(ordering, "  ")],
                [rows[i].session_id for i in (3, 2, 1, 0)],
            )
        restored = tuple(
            ConversationSummary.model_validate_json(r.model_dump_json()) for r in rows
        )
        self.assertEqual(
            rank_sessions(rows, "strasse"), rank_sessions(restored, "strasse")
        )

    def test_fuzzy_cutoffs_do_not_guess_short_names_or_identifiers(self) -> None:
        rows = (summary(1, "cat"), summary(2, "parser"), summary(3, "abcdefghij"))
        self.assertEqual(rank_sessions(rows, "cot"), ())
        self.assertEqual(rank_sessions(rows, "parxer")[0].distance, 1)
        self.assertEqual(rank_sessions(rows, "pazxer"), ())
        self.assertEqual(rank_sessions(rows, "abcdxxghij")[0].distance, 2)
        self.assertEqual(rank_sessions(rows, "abcxxxghij"), ())
        self.assertEqual(rank_sessions((summary(1, None),), "0" * 31 + "2"), ())

    def test_fuzzy_distance_then_saved_time_then_id_break_ties(self) -> None:
        rows = (
            summary(4, "abcxxfgh", 999),
            summary(3, "abcdefgx", 2),
            summary(2, "abcdefgx", 2),
            summary(1, "abcdefgx", 1),
        )
        self.assertEqual(
            [m.summary.session_id for m in rank_sessions(rows, "abcdefgh")],
            [rows[i].session_id for i in (2, 1, 3, 0)],
        )

    def test_query_and_catalog_bounds_reject_without_echoing_input(self) -> None:
        for query in ("PRIVATE" * 18, "PRIVATE\n", "PRIVATE\x1b", "PRIVATE\udcff"):
            with self.assertRaises(SessionSelectionError) as caught:
                rank_sessions((), query)
            self.assertNotIn("PRIVATE", str(caught.exception))
        rows = tuple(summary(i, "\ufb03" * 120) for i in range(1000))
        self.assertEqual(len(rank_sessions(rows, "\ufb03" * 120)), 1000)
        with self.assertRaisesRegex(SessionSelectionError, "1,000"):
            rank_sessions((*rows, summary(1000, None)), "")
        with self.assertRaisesRegex(SessionSelectionError, "metadata bound"):
            rank_sessions((rows[0].model_copy(update={"session_name": "x" * 121}),), "")

    def test_banded_distance_agrees_with_exhaustive_reference(self) -> None:
        def reference(left: str, right: str) -> int:
            row = list(range(len(right) + 1))
            for i, char in enumerate(left, 1):
                following = [i]
                for j, other in enumerate(right, 1):
                    following.append(
                        min(row[j] + 1, following[-1] + 1, row[j - 1] + (char != other))
                    )
                row = following
            return row[-1]

        words = [
            "".join(chars)
            for size in range(5)
            for chars in itertools.product("ab", repeat=size)
        ]
        for left, right, limit in itertools.product(words, words, (1, 2)):
            self.assertEqual(
                bounded_edit_distance(left, right, limit),
                min(limit + 1, reference(left, right)),
                (left, right, limit),
            )

    def test_worst_case_fuzzy_candidate_work_is_bounded(self) -> None:
        # Case-fold expansion reaches 360 characters; only a five-cell band is
        # visited per character, with no quadratic matrix or catalog-dependent cutoff.
        rows = tuple(summary(i, "\ufb03" * 119 + "x") for i in range(1000))
        with patch(
            "mos_eisley.conversation_resume_rank.bounded_edit_distance",
            wraps=bounded_edit_distance,
        ) as distance:
            matches = rank_sessions(rows, "\ufb03" * 119 + "y")
        self.assertEqual(len(matches), 1000)
        self.assertEqual(distance.call_count, 2000)
        self.assertTrue(all(m.distance == 1 for m in matches))


class ResumeRankingCatalogTests(TestCase):
    def test_backends_have_equal_ranking_with_no_search_io_or_exact_lookup_drift(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            states = tuple(
                ConversationController.fresh(root, demo_cassette()).model_copy(
                    update={"session_name": name}
                )
                for name in ("Parser", "Parser cleanup", "Parsar", None)
            )
            catalogs: list[tuple[ResumeMatch, ...]] = []
            for sqlite in (False, True):
                storage = root / ("sqlite" if sqlite else "json")
                backend = SQLiteConversationStore if sqlite else ConversationStore
                for state in states:
                    with backend(storage, state.session_id, root) as store:
                        store.save(state)
                catalog = resume_catalog(storage, root, sqlite=sqlite)
                # Equivalent saved times, independent of backend commit latency.
                rows = tuple(
                    s.model_copy(update={"modified_ns": 42}) for s in catalog.sessions
                )
                with (
                    patch("builtins.open", side_effect=AssertionError("search IO")),
                    patch("os.open", side_effect=AssertionError("search IO")),
                ):
                    catalogs.append(rank_sessions(rows, "parser"))
                self.assertEqual(len(named_sessions(catalog, "PARSER")), 1)
                self.assertEqual(named_sessions(catalog, "parse"), ())
                other = root / "other"
                other.mkdir(exist_ok=True)
                foreign = ConversationController.fresh(
                    other, demo_cassette()
                ).model_copy(
                    update={
                        "session_name": "Foreign secret",
                        "entries": (ConversationEntry(text="Transcript sentinel"),),
                    }
                )
                with backend(storage, foreign.session_id, other) as store:
                    store.save(foreign)
                admitted = resume_catalog(storage, root, sqlite=sqlite)
                self.assertEqual(rank_sessions(admitted.sessions, "foreign secret"), ())
                other_catalog = resume_catalog(storage, other, sqlite=sqlite)
                self.assertEqual(len(other_catalog.sessions), 1)
                self.assertEqual(
                    rank_sessions(other_catalog.sessions, "transcript sentinel"), ()
                )
                self.assertEqual(
                    rank_sessions(
                        resume_catalog(storage, other, sqlite=sqlite).sessions, "parser"
                    ),
                    (),
                )
                # A second synthetic owner cannot even admit this private store.
                with (
                    patch("os.getuid", return_value=os.getuid() + 1),
                    self.assertRaises(ValueError),
                ):
                    resume_catalog(storage, root, sqlite=sqlite)
            self.assertEqual(
                [(m.summary.session_id, m.basis, m.distance) for m in catalogs[0]],
                [(m.summary.session_id, m.basis, m.distance) for m in catalogs[1]],
            )

    def test_sqlite_thousand_session_boundary_without_transcript_hydration(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / "sessions"
            base = ConversationController.fresh(root, demo_cassette())
            for i in range(1000):
                state = base.model_copy(
                    update={"session_id": f"{i:032x}", "session_name": f"Parser {i}"}
                )
                with SQLiteConversationStore(storage, state.session_id, root) as store:
                    store.save(state)
            with (
                patch.object(
                    SQLiteConversationStore,
                    "load",
                    side_effect=AssertionError("hydration"),
                ),
                patch.object(
                    SQLiteConversationStore,
                    "load_working",
                    side_effect=AssertionError("hydration"),
                ),
            ):
                catalog = resume_catalog(storage, root, sqlite=True)
                self.assertEqual(len(rank_sessions(catalog.sessions, "parser")), 1000)
            state = base.model_copy(update={"session_id": f"{1000:032x}"})
            with SQLiteConversationStore(storage, state.session_id, root) as store:
                store.save(state)
            with self.assertRaisesRegex(SessionSelectionError, "1,000"):
                resume_catalog(storage, root, sqlite=True)
