"""Explicit local subscription inference through an owner-installed Codex client."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import signal
import stat
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock, Turn, Usage
from mos_eisley.platform.files import UnsupportedPlatformError
from mos_eisley.platform.posix_storage_native import NativeRootQueries
from mos_eisley.platform.storage import StorageAdmissionError
from mos_eisley.tools.mcp_schema import compile_schema, valid_instance

CLIENT_VERSION = "0.161.0"
PROVIDER = "openai_subscription"
MAX_INPUT = 128_000
MAX_EVENTS = 1_000_000
MAX_STDERR = 32_000
NATIVE_PROFILE = ("gpt-6-sol", "medium")
_OBJECT = TypeAdapter(dict[str, JsonValue])
CLIENT_ENVIRONMENT = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "CODEX_HOME",
}
# This is an exact-client compatibility boundary, not a promise that future
# native tool features inherit these restrictions.
_DISABLED = (
    "shell_tool",
    "unified_exec",
    "shell_snapshot",
    "view_image",
    "image_generation",
    "apps",
    "plugins",
    "remote_plugin",
    "hooks",
    "multi_agent",
    "code_mode_host",
    "js_repl",
    "browser_use",
    "computer_use",
    "sleep_tool",
    "skill_search",
    "skill_mcp_dependency_install",
    "tool_suggest",
    "workspace_dependencies",
    "worktrees",
    "goals",
    "daemon_auto_start",
    "unbounded_connection_retries",
)


def write_receipt(directory: int, name: str, value: dict[str, JsonValue]) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, allow_nan=False))
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(directory)


@contextlib.contextmanager
def new_attempt(path: Path) -> Generator[int, None, None]:
    """Anchor receipt writes to checked, ACL-free owner directories."""
    try:
        parent = os.open(
            path.absolute().parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError:
        raise ProviderError("Subscription attempt parent is inadmissible") from None
    attempt: int | None = None
    try:
        try:
            query = NativeRootQueries()
            info = os.fstat(parent)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise StorageAdmissionError("attempt parent is not private")
            query.protection(parent, stat.S_IMODE(info.st_mode))
            os.mkdir(path.name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
            attempt = os.open(
                path.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            info = os.fstat(attempt)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise StorageAdmissionError("attempt directory is not private")
            query.protection(attempt, stat.S_IMODE(info.st_mode))
        except FileExistsError:
            raise
        except (
            OSError,
            ValueError,
            AttributeError,
            StorageAdmissionError,
            UnsupportedPlatformError,
        ):
            raise ProviderError(
                "Subscription storage protection is unsupported"
            ) from None
        yield attempt
    finally:
        if attempt is not None:
            os.close(attempt)
        os.close(parent)


def select_client(explicit: Path | None = None, *, name: str = "codex") -> Path:
    """Exclude project-local executables and relative PATH entries."""
    project = Path.cwd().resolve()
    if explicit is None:
        directories = [
            entry
            for entry in os.environ.get("PATH", "").split(os.pathsep)
            if entry
            and Path(entry).is_absolute()
            and (
                project == Path.home().resolve()
                or not Path(entry).resolve().is_relative_to(project)
            )
        ]
        found = shutil.which(name, path=os.pathsep.join(directories))
        if found is None:
            raise ProviderError("Install the official Codex client first")
        explicit = Path(found)
    if not explicit.is_absolute():
        raise ProviderError("Subscription client must have an absolute path")
    resolved = explicit.resolve(strict=True)
    if (
        project != Path.home().resolve() and resolved.is_relative_to(project)
    ) or not resolved.is_file():
        raise ProviderError("Subscription client cannot come from the active project")
    return resolved


async def read_stream(stream: asyncio.StreamReader, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await stream.read(4096):
        size += len(chunk)
        if size > limit:
            raise ProviderError("Subscription client exceeded its output limit")
        chunks.append(chunk)
    return b"".join(chunks)


async def _stop(process: asyncio.subprocess.Process) -> None:
    # Signal the session even if its leader exited while descendants hold pipes.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), 1)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    await asyncio.wait_for(process.wait(), 2)


async def invoke(
    executable: Path,
    arguments: tuple[str, ...],
    cwd: Path,
    *,
    data: bytes = b"",
    timeout: float = 15,
    output_limit: int = MAX_EVENTS,
) -> tuple[int, bytes, bytes]:
    if os.name != "posix":
        raise ProviderError("This subscription client requires macOS or Linux")
    environment = {
        key: value for key, value in os.environ.items() if key in CLIENT_ENVIRONMENT
    }
    try:
        process = await asyncio.create_subprocess_exec(
            str(executable),
            *arguments,
            cwd=cwd,
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except OSError:
        raise ProviderError("Subscription client could not start") from None
    assert process.stdin is not None and process.stdout is not None
    assert process.stderr is not None
    readers = (
        asyncio.create_task(read_stream(process.stdout, output_limit)),
        asyncio.create_task(read_stream(process.stderr, MAX_STDERR)),
    )
    try:
        async with asyncio.timeout(timeout):
            process.stdin.write(data)
            await process.stdin.drain()
            process.stdin.close()
            stdout, stderr = await asyncio.gather(*readers)
            code = await process.wait()
        return code, stdout, stderr
    except TimeoutError:
        raise ProviderError(
            "Subscription request timed out; Mos will not repeat this invocation",
            failure_kind="provider_timeout",
            failure_stage="response",
        ) from None
    except OSError:
        raise ProviderError("Subscription client exchange failed") from None
    finally:
        for reader in readers:
            reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        await _stop(process)


async def status(executable: Path) -> dict[str, JsonValue]:
    """Read native authentication metadata; never open the credential cache."""
    with tempfile.TemporaryDirectory(prefix="mos-subscription-status-") as directory:
        cwd = Path(directory)
        code, raw, _ = await invoke(executable, ("--version",), cwd, output_limit=4096)
        compatible = code == 0 and raw.strip() == f"codex-cli {CLIENT_VERSION}".encode()
        if not compatible:
            return {"client_version_supported": False, "subscription_signed_in": False}
        code, raw, diagnostic = await invoke(
            executable,
            ("login", "status"),
            cwd,
            output_limit=4096,
        )
        message = raw + diagnostic
        signed_in = code == 0 and b"Logged in using ChatGPT" in message
        return {"client_version_supported": True, "subscription_signed_in": signed_in}


def parse_result(raw: bytes, max_text: int) -> ModelResponse:
    """Admit one complete text-only turn; diagnostics and reasoning stay private."""
    if len(raw) > MAX_EVENTS or not 1 <= max_text <= 64_000:
        raise ProviderError("Subscription event or output ceiling is invalid")
    started = False
    completed = False
    thread_id = ""
    answer = ""
    usage: Usage | None = None
    try:
        for line in raw.splitlines():
            event = _OBJECT.validate_json(line, strict=True)
            kind = event.get("type")
            if completed:
                raise ValueError("events after completion")
            if kind == "thread.started" and not thread_id and not started:
                selected = event.get("thread_id")
                if not isinstance(selected, str) or not 1 <= len(selected) <= 200:
                    raise ValueError("invalid thread identity")
                thread_id = selected
            elif kind == "turn.started" and thread_id and not started:
                started = True
            elif kind == "item.completed" and thread_id and not started:
                item = event.get("item")
                if (
                    not isinstance(item, dict)
                    or item.get("type") != "error"
                    or item.get("message")
                    != (
                        "Code Mode is unavailable because code-mode host is disabled. "
                        "Code mode will fail closed; enable `features.code_mode_host` "
                        "and install `codex-code-mode-host`."
                    )
                ):
                    raise ValueError("unsupported startup warning")
            elif kind in {"item.started", "item.updated", "item.completed"} and started:
                item = event.get("item")
                if not isinstance(item, dict) or item.get("type") not in {
                    "agent_message",
                    "reasoning",
                }:
                    raise ValueError("native tool or unsupported item")
                if kind == "item.completed" and item.get("type") == "agent_message":
                    text = item.get("text")
                    if (
                        not isinstance(text, str)
                        or not text
                        or len(text.encode()) > max_text
                    ):
                        raise ValueError("invalid or oversized answer")
                    answer = text
            elif kind == "turn.completed" and started and answer:
                values = event.get("usage")
                if not isinstance(values, dict):
                    raise ValueError("missing usage")
                counts = tuple(
                    values.get(key)
                    for key in (
                        "input_tokens",
                        "output_tokens",
                        "cached_input_tokens",
                        "cache_write_input_tokens",
                        "reasoning_output_tokens",
                    )
                )
                if any(
                    type(count) is not int or not 0 <= count <= 1_000_000_000
                    for count in counts
                ):
                    raise ValueError("invalid usage")
                incoming, outgoing, cached, cache_write, reasoning = counts
                assert isinstance(incoming, int) and isinstance(outgoing, int)
                assert isinstance(cached, int)
                assert isinstance(cache_write, int) and isinstance(reasoning, int)
                if cached > incoming or cache_write > incoming or reasoning > outgoing:
                    raise ValueError("invalid cached usage")
                usage = Usage(
                    unit="tokens",
                    input=incoming,
                    output=outgoing,
                    cache_read=cached,
                    cache_write=cache_write,
                    reasoning=reasoning,
                )
                completed = True
            else:
                raise ValueError("failed or invalid event sequence")
    except (ValueError, TypeError, RecursionError):
        raise ProviderError(
            "Subscription client returned an inadmissible turn"
        ) from None
    if not completed or usage is None:
        raise ProviderError(
            "Subscription client did not complete; do not retry automatically"
        )
    return ModelResponse(
        turn=Turn(role="assistant", blocks=(TextBlock(text=answer),)),
        stop_reason="end_turn",
        usage=usage,
        provider_request_id=thread_id,
    )


class CodexSubscriptionClient:
    """A separate text/structured-output route, never an implicit API fallback."""

    def __init__(
        self,
        executable: Path,
        attempt: Path,
        *,
        allow_data_transfer: bool,
        allow_subscription_usage: bool,
        timeout: float = 60,
        authorized_profile: tuple[str, str] | None = None,
        dispatch_guard: Callable[[], None] | None = None,
    ) -> None:
        if os.name != "posix":
            raise ProviderError("This subscription client requires macOS or Linux")
        if allow_data_transfer is not True or allow_subscription_usage is not True:
            raise ValueError(
                "Subscription inference requires transfer and usage consent"
            )
        if not 1 <= timeout <= 120:
            raise ValueError("Subscription request deadline must be 1–120 seconds")
        self.executable = executable
        self.attempt = attempt
        self.timeout = timeout
        self.profile = NATIVE_PROFILE
        if authorized_profile is not None:
            from mos_eisley.subscription_authorization import subscription_registry

            model, effort = authorized_profile
            from pydantic import TypeAdapter

            from mos_eisley.core.protocol import Effort

            selected = TypeAdapter[Effort](Effort).validate_python(effort)
            resolved = subscription_registry().resolve(PROVIDER, model, selected)
            if resolved.substituted:
                raise ValueError("Authorized native profile cannot substitute effort")
            self.profile = (model, selected)
        self.dispatch_guard = dispatch_guard

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if (request.model, request.effort) != self.profile:
            raise ProviderError(
                "This model/effort is outside the native compatibility set"
            )
        if (
            request.provider != PROVIDER
            or request.tools
            or any(
                not isinstance(block, TextBlock)
                for turn in request.turns
                for block in turn.blocks
            )
        ):
            raise ProviderError("Subscription request must use its text-only route")
        payload = json.dumps(
            {
                "instructions": request.system,
                "messages": [
                    {
                        "role": turn.role,
                        "text": "\n".join(
                            block.text
                            for block in turn.blocks
                            if isinstance(block, TextBlock)
                        ),
                    }
                    for turn in request.turns
                ],
            },
            ensure_ascii=False,
        ).encode()
        if len(payload) > MAX_INPUT:
            raise ProviderError("Subscription request exceeds its input limit")
        output_schema = None
        if request.response_format is not None:
            output_schema, _ = compile_schema(request.response_format.json_schema)
        with new_attempt(self.attempt) as attempt:
            write_receipt(
                attempt,
                "request.json",
                {
                    "schema": 1,
                    "provider": PROVIDER,
                    "model": request.model,
                    "effort": request.effort,
                    "client_version": CLIENT_VERSION,
                    "request_sha256": hashlib.sha256(payload).hexdigest(),
                    "billing": "subscription_usage_unverified",
                    "state": "reserved",
                },
            )
            readiness = await status(self.executable)
            if not all(readiness.values()):
                raise ProviderError(
                    "A supported client signed in with ChatGPT is required"
                )
            with tempfile.TemporaryDirectory(
                prefix="mos-subscription-turn-"
            ) as directory:
                cwd = Path(directory)
                arguments = [
                    "--no-daemon",
                    "exec",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--strict-config",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "read-only",
                    "--json",
                    "--color",
                    "never",
                    "--model",
                    request.model,
                ]
                for setting in (
                    'model_provider="openai"',
                    'forced_login_method="chatgpt"',
                    f'model_reasoning_effort="{request.effort}"',
                    'approval_policy="never"',
                    'web_search="disabled"',
                    "project_doc_max_bytes=0",
                    'history.persistence="none"',
                    "features.skip_host_skill_discovery=true",
                    "suppress_unstable_features_warning=true",
                ):
                    arguments.extend(("-c", setting))
                for feature in _DISABLED:
                    arguments.extend(("--disable", feature))
                if output_schema is not None:
                    schema = cwd / "output-schema.json"
                    schema.write_text(json.dumps(output_schema))
                    arguments.extend(("--output-schema", str(schema)))
                arguments.append("-")
                if self.dispatch_guard is not None:
                    self.dispatch_guard()
                write_receipt(
                    attempt, "dispatch.json", {"schema": 1, "state": "dispatch_started"}
                )
                code, raw, _ = await invoke(
                    self.executable,
                    tuple(arguments),
                    cwd,
                    data=payload,
                    timeout=self.timeout,
                )
                if code != 0:
                    raise ProviderError(
                        "Subscription inference failed; "
                        "Mos will not repeat this invocation"
                    )
                limit = min(request.max_text_output_bytes or request.max_output, 64_000)
                result = parse_result(raw, limit)
                if len(result.model_dump_json().encode()) > request.max_output:
                    raise ProviderError(
                        "Subscription response exceeded its byte ceiling"
                    )
                if (
                    request.max_output_tokens is not None
                    and result.usage.output > request.max_output_tokens
                ):
                    raise ProviderError(
                        "Subscription response exceeded the accepted token ceiling"
                    )
                if output_schema is not None:
                    text = result.turn.blocks[0]
                    assert isinstance(text, TextBlock)
                    try:
                        value: object = json.loads(text.text)
                        valid = valid_instance(output_schema, value)
                    except ValueError:
                        valid = False
                    if not valid:
                        raise ProviderError(
                            "Subscription response violated the output contract"
                        )
                write_receipt(
                    attempt,
                    "completion.json",
                    {
                        "schema": 1,
                        "state": "completed",
                        "usage": result.usage.model_dump(mode="json"),
                        "response_sha256": hashlib.sha256(
                            result.model_dump_json().encode()
                        ).hexdigest(),
                    },
                )
                return result
