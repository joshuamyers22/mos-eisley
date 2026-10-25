"""Deterministic discovery over an already admitted, bounded metadata catalog."""

from dataclasses import dataclass
from typing import Literal

from mos_eisley.conversation_name import SessionSelectionError, name_key
from mos_eisley.run.conversation_names import MAX_RESUME_CATALOG
from mos_eisley.run.conversation_store import ConversationSummary

MAX_QUERY_CHARS = 120
MAX_FUZZY_EDITS = 2
MatchBasis = Literal[
    "recent",
    "exact_id",
    "exact_name",
    "name_prefix",
    "name_words",
    "id_fragment",
    "fuzzy_name",
]
_PRIORITY: dict[MatchBasis, int] = {
    "recent": 0,
    "exact_id": 0,
    "exact_name": 1,
    "name_prefix": 2,
    "name_words": 3,
    "id_fragment": 3,
    "fuzzy_name": 4,
}
_LABELS: dict[MatchBasis, str] = {
    "recent": "Recent",
    "exact_id": "Exact ID",
    "exact_name": "Exact name",
    "name_prefix": "Name prefix",
    "name_words": "All words",
    "id_fragment": "ID fragment",
    "fuzzy_name": "Similar name",
}


@dataclass(frozen=True)
class ResumeMatch:
    summary: ConversationSummary
    basis: MatchBasis
    distance: int = 0

    @property
    def label(self) -> str:
        label = _LABELS[self.basis]
        if self.basis == "fuzzy_name":
            label += f" ({self.distance} edit{'s' if self.distance != 1 else ''})"
        return label


def bounded_edit_distance(left: str, right: str, limit: int) -> int:
    """Banded Levenshtein distance; limit + 1 means outside the accepted band.

    At most five cells per input character and constant band storage. No matrix
    allocation or unbounded similarity heuristic, even for Unicode case folding.
    """
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = {i: i for i in range(min(len(right), limit) + 1)}
    for i, char in enumerate(left, 1):
        current: dict[int, int] = {}
        if i <= limit:
            current[0] = i
        for j in range(max(1, i - limit), min(len(right), i + limit) + 1):
            current[j] = min(
                previous.get(j, limit + 1) + 1,
                current.get(j - 1, limit + 1) + 1,
                previous.get(j - 1, limit + 1) + (char != right[j - 1]),
            )
        if not current or min(current.values()) > limit:
            return limit + 1
        previous = current
    return min(limit + 1, previous.get(len(right), limit + 1))


def _match(summary: ConversationSummary, query: str) -> ResumeMatch | None:
    if not query:
        return ResumeMatch(summary, "recent")
    if query == summary.session_id:
        return ResumeMatch(summary, "exact_id")
    name = name_key(summary.session_name or "")
    if name and name == query:
        return ResumeMatch(summary, "exact_name")
    if name and name.startswith(query):
        return ResumeMatch(summary, "name_prefix")
    if name and all(word in name for word in query.split()):
        return ResumeMatch(summary, "name_words")
    # Preserve literal partial-ID discovery, without fuzzy matching identifiers.
    if query in summary.session_id:
        return ResumeMatch(summary, "id_fragment")
    if len(query) < 4 or not name:
        return None
    limit = 1 if len(query) < 8 else MAX_FUZZY_EDITS
    distance = min(
        bounded_edit_distance(query, candidate, limit)
        for candidate in (name, *name.split())
    )
    if distance <= limit:
        return ResumeMatch(summary, "fuzzy_name", distance)
    return None


def rank_sessions(
    sessions: tuple[ConversationSummary, ...], query: str
) -> tuple[ResumeMatch, ...]:
    """Rank metadata only; never load, choose, resume or broaden catalog scope.

    Names and raw queries are bounded to 120 code points (at most 360 after
    casefold/NFC). Fuzzy candidates are the full name and its words, with a band
    of at most two edits. Catalogs have at most 1,000 summaries.
    """
    if len(query) > MAX_QUERY_CHARS or any(not c.isprintable() for c in query):
        raise SessionSelectionError("Search requires at most 120 printable characters.")
    if len(sessions) > MAX_RESUME_CATALOG:
        raise SessionSelectionError("Resume search exceeds 1,000 sessions; use an ID.")
    if any(len(s.session_name or "") > MAX_QUERY_CHARS for s in sessions):
        raise SessionSelectionError("Resume name exceeds the search metadata bound.")
    normalized = name_key(query)
    matches = (
        match
        for summary in sessions
        if (match := _match(summary, normalized)) is not None
    )
    return tuple(
        sorted(
            matches,
            key=lambda match: (
                _PRIORITY[match.basis],
                match.distance,
                -match.summary.modified_ns,
                match.summary.session_id,
            ),
        )
    )
