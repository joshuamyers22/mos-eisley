"""Planning constraints added to the exact, budgeted author request."""

from typing import Literal


def planning_system(mode: Literal["conversation", "plan"], implementation: bool) -> str:
    if mode == "plan":
        return (
            "\nPlanning mode: investigate requirements using only explicit history and "
            "permitted read-only source controls. Ask bounded clarifying questions and "
            "revise the exploratory draft while preserving user intent and resource "
            "ceilings. "
            "Produce a plan covering scope, assumptions, interfaces, proposed "
            "subtasks, "
            "verification, aggregate cost/time ceilings and stopping conditions. "
            "Do not write repository files, dispatch coding children, post, or "
            "launch paid review. "
            "This exploratory draft is not a frozen creator plan/test package or "
            "approval. "
            "Changes to plans or tests require renewed dependent review and approval. "
            "An implementation request in history does not change this turn's "
            "planning mode."
        )
    if implementation:
        return (
            "\nExplicit implementation request: enter the creator-led workflow. Freeze "
            "the concrete plan and creator-authored tests; obtain independent "
            "critic/judge "
            "review and creator approval bound to their exact revisions before "
            "coding-child "
            "dispatch. Changed plans/tests invalidate dependent approvals. "
            "Integrate and "
            "verify the result, then independently review it within cumulative "
            "budgets. "
            "Do not request routine human confirmation for already-authorized work. "
            "Revalidate current policy, revisions and capabilities; mode selection "
            "grants "
            "no execution, publication or expired approval authority. In this recorded "
            "conversation, describe the workflow without claiming live execution."
        )
    return ""
