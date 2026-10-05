"""Exact, unpaid coding briefs and patch handoffs; host approval is separate."""

import ast
import builtins
import re
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_agents import ImplementationAssignment
from mos_eisley.core.models import Contract, Digest, Text, canonical_bytes, digest


def safe_code_path(path: str) -> str:
    if (
        not re.fullmatch(r"[A-Za-z0-9_/-]+\.py", path)
        or any(p in {"", ".", ".."} or p.startswith(".") for p in path.split("/"))
        or len(path) > 240
    ):
        raise ValueError("Coding paths must be bounded relative Python source paths.")
    return path


PURE_BUILTINS = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "max",
        "min",
        "range",
        "reversed",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
        "ValueError",
        "TypeError",
    }
)
PURE_METHODS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "pop",
        "remove",
        "clear",
        "copy",
        "count",
        "index",
        "reverse",
        "sort",
        "get",
        "items",
        "keys",
        "values",
        "setdefault",
        "update",
        "add",
        "discard",
        "lower",
        "upper",
        "strip",
        "split",
        "join",
        "replace",
        "startswith",
        "endswith",
    }
)


def validate_pure_source(content: str) -> None:
    """Admit a bounded Python algorithm subset; no imports or runtime introspection.

    This is a capability restriction in addition to Docker, not a general Python
    sandbox or a correctness proof. Caller-authored tests remain immutable.
    """
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError("Coding source must be valid bounded Python.") from error
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if not functions or any(
        not isinstance(n, ast.FunctionDef)
        and not (
            isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )
        for n in tree.body
    ):
        raise ValueError("Local coding supports pure function modules only.")
    nodes = tuple(ast.walk(tree))
    if len(nodes) > 10_000:
        raise ValueError("Coding source exceeds its syntax-node bound.")
    forbidden = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.AsyncFunctionDef,
        ast.AsyncFor,
        ast.AsyncWith,
        ast.Await,
        ast.Global,
        ast.Nonlocal,
        ast.With,
        ast.Delete,
        ast.Lambda,
    )
    for node in nodes:
        if isinstance(node, forbidden):
            raise ValueError("Coding source expands the pure Python capability scope.")
        if isinstance(node, ast.Name) and (
            node.id.startswith("__") or node.id in set(dir(builtins)) - PURE_BUILTINS
        ):
            raise ValueError("Runtime introspection is unavailable to coding children.")
        if isinstance(node, ast.Attribute) and (
            node.attr not in PURE_METHODS or isinstance(node.ctx, (ast.Store, ast.Del))
        ):
            raise ValueError("Coding children may use only approved value methods.")
        if isinstance(node, ast.Call) and not (
            (
                isinstance(node.func, ast.Name)
                and node.func.id in PURE_BUILTINS | functions
            )
            or (isinstance(node.func, ast.Attribute) and node.func.attr in PURE_METHODS)
        ):
            raise ValueError(
                "Coding calls require an approved pure function or builtin."
            )
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list or node.name.startswith("__"):
                raise ValueError("Coding functions cannot register runtime hooks.")
            for default in (
                *node.args.defaults,
                *(d for d in node.args.kw_defaults if d is not None),
            ):
                try:
                    ast.literal_eval(default)
                except (ValueError, TypeError, SyntaxError) as error:
                    raise ValueError(
                        "Coding defaults must be inert literals."
                    ) from error
            annotations = [
                a.annotation
                for a in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
                if a.annotation is not None
            ]
            if node.returns is not None:
                annotations.append(node.returns)
            if any(
                not isinstance(a, ast.Constant)
                and not (isinstance(a, ast.Name) and a.id in PURE_BUILTINS)
                for a in annotations
            ):
                raise ValueError(
                    "Coding annotations must be inert literals or builtin names."
                )


class CodeFile(Contract):
    path: Annotated[str, Field(min_length=1, max_length=240)]
    content: Annotated[str, Field(max_length=64_000)]

    @model_validator(mode="after")
    def safe_path(self) -> Self:
        safe_code_path(self.path)
        if "\x00" in self.content:
            raise ValueError("Source must be text without NUL bytes.")
        return self

    @property
    def sha256(self) -> str:
        return digest(self.content.encode())


class CodeSnapshot(Contract):
    files: Annotated[tuple[CodeFile, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def bounded_unique(self) -> Self:
        paths = tuple(f.path for f in self.files)
        if paths != tuple(sorted(set(paths))) or len(canonical_bytes(self)) > 128_000:
            raise ValueError("Snapshot must be sorted, unique and bounded.")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class CodingBrief(Contract):
    assignment: ImplementationAssignment
    base_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    snapshot: CodeSnapshot
    plan: Text
    interfaces: Text
    acceptance: Text
    owned_paths: Annotated[tuple[str, ...], Field(min_length=1, max_length=16)]
    test_paths: Annotated[tuple[str, ...], Field(min_length=1, max_length=16)]
    wall_seconds: Annotated[int, Field(ge=1, le=20)] = 10
    depth: Literal[1] = 1
    source_policy: Literal["pure_python_v1"] = "pure_python_v1"
    permitted_tools: tuple[Literal["write_owned_files"], ...] = ("write_owned_files",)

    @model_validator(mode="after")
    def frozen_scope(self) -> Self:
        files = {f.path: f for f in self.snapshot.files}
        for paths in (self.owned_paths, self.test_paths):
            if paths != tuple(sorted(set(paths))):
                raise ValueError("File ownership must be sorted and unique.")
            for path in paths:
                safe_code_path(path)
        if (
            set(self.owned_paths) & set(self.test_paths)
            or any(p.startswith("tests/") for p in self.owned_paths)
            or any(not p.startswith("tests/test_") for p in self.test_paths)
            or not set(self.test_paths) <= files.keys()
            or set(files)
            != (set(self.owned_paths) & files.keys()) | set(self.test_paths)
            or self.permitted_tools != ("write_owned_files",)
            or self.assignment.plan_sha256 != digest(self.plan.encode())
            or self.assignment.tests_sha256 != self.tests_sha256
            or self.assignment.provider != "fixture"
            or self.assignment.worktree is None
            or self.assignment.allowance.cost_microusd
            or self.assignment.allowance.attempts != 1
            or self.assignment.allowance.review_rounds
            or self.assignment.allowance.correction_cycles
        ):
            raise ValueError(
                "Coding requires an exact unpaid source/test/ownership brief."
            )
        for file in self.snapshot.files:
            if file.path in self.owned_paths:
                validate_pure_source(file.content)
        return self

    @property
    def tests_sha256(self) -> str:
        return CodeSnapshot(
            files=tuple(f for f in self.snapshot.files if f.path in self.test_paths)
        ).sha256

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class FileChange(Contract):
    file: CodeFile
    before_sha256: Digest | None


class CodingPatch(Contract):
    brief_sha256: Digest
    changes: Annotated[tuple[FileChange, ...], Field(min_length=1, max_length=16)]
    summary: Text

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))

    def apply(self, brief: CodingBrief) -> CodeSnapshot:
        files = {f.path: f for f in brief.snapshot.files}
        paths = tuple(c.file.path for c in self.changes)
        if self.brief_sha256 != brief.sha256 or paths != tuple(sorted(set(paths))):
            raise ValueError(
                "Patch differs from its exact brief or has duplicate paths."
            )
        for change in self.changes:
            previous = files.get(change.file.path)
            if (
                change.file.path not in brief.owned_paths
                or change.before_sha256
                != (None if previous is None else previous.sha256)
                or previous == change.file
            ):
                raise ValueError(
                    "Patch changes unowned, protected, stale or unchanged files."
                )
            validate_pure_source(change.file.content)
            files[change.file.path] = change.file
        return CodeSnapshot(files=tuple(files[p] for p in sorted(files)))


class CodingReview(Contract):
    """Receipt supplied by the trusted host critic/judge adapter, never by a child."""

    brief_sha256: Digest
    plan_sha256: Digest
    tests_sha256: Digest
    phase: Literal["plan_tests", "final"]
    patch_sha256: Digest | None = None
    critic_sha256: Digest
    judge_sha256: Digest
    decision: Literal["accept", "reject"]

    def require(self, brief: CodingBrief, patch: CodingPatch | None = None) -> None:
        if (
            self.brief_sha256 != brief.sha256
            or self.plan_sha256 != brief.assignment.plan_sha256
            or self.tests_sha256 != brief.assignment.tests_sha256
            or self.phase != ("plan_tests" if patch is None else "final")
            or self.patch_sha256 != (None if patch is None else patch.sha256)
            or self.decision != "accept"
        ):
            raise ValueError(
                "Creator workflow needs current accepted plan/test or final review."
            )


class CodingVerification(Contract):
    snapshot_sha256: Digest
    tests_sha256: Digest
    passed: bool
    output_sha256: Digest


class CodingHandoff(Contract):
    patch: CodingPatch
    verification: CodingVerification
    diff: Annotated[str, Field(min_length=1, max_length=128_000)]


class CodingRetention(Contract):
    brief: CodingBrief
    plan_review: CodingReview
    handoff: CodingHandoff | None = None
    final_review: CodingReview | None = None
    integration_state: Literal["pending", "integrating", "integrated", "uncertain"] = (
        "pending"
    )
    integrated_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None = None
    final_verification: CodingVerification | None = None
    applied_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None = None

    @model_validator(mode="after")
    def exact_retained_handoff(self) -> Self:
        self.plan_review.require(self.brief)
        if self.handoff is not None:
            snapshot = self.handoff.patch.apply(self.brief)
            if (
                self.handoff.verification.snapshot_sha256 != snapshot.sha256
                or self.handoff.verification.tests_sha256
                != self.brief.assignment.tests_sha256
            ):
                raise ValueError(
                    "Handoff verification differs from its protected tests or patch."
                )
        if self.final_review is not None:
            if self.handoff is None:
                raise ValueError("Final review requires a retained patch.")
            self.final_review.require(self.brief, self.handoff.patch)
        if self.integration_state != "pending" and (
            self.final_review is None
            or self.handoff is None
            or not self.handoff.verification.passed
        ):
            raise ValueError("Integration requires a tested and reviewed patch.")
        if (self.integration_state == "integrated") != (
            self.integrated_commit is not None and self.final_verification is not None
        ):
            raise ValueError(
                "Integrated coding needs final verification and commit identity."
            )
        if self.integration_state == "pending" and self.applied_commit is not None:
            raise ValueError("Pending coding cannot claim an applied commit.")
        if (
            self.integration_state == "integrated"
            and self.applied_commit != self.integrated_commit
        ):
            raise ValueError("Integrated and applied commits must agree.")
        if self.final_verification is not None and (
            self.handoff is None
            or not self.final_verification.passed
            or self.final_verification.snapshot_sha256
            != self.handoff.verification.snapshot_sha256
            or self.final_verification.tests_sha256
            != self.brief.assignment.tests_sha256
        ):
            raise ValueError(
                "Final verification differs from the integrated patch/tests."
            )
        return self


class CodingIntegrationApproval(Contract):
    owner_uid: Annotated[int, Field(ge=0)]
    parent_session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    child_id: Text
    handoff_sha256: Digest
    review_sha256: Digest
    expires_at: Annotated[float, Field(ge=0)]
