"""Nonblocking interactive notices; running work is never restarted by an update."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import Callable, Generator
from pathlib import Path

from mos_eisley.conversation_input import ConversationInput, ConversationInputQueue


def runtime_root() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    executable = Path(sys.executable).resolve()
    candidate = executable.parent.parent.parent
    if (
        executable.parent.parent.name == "releases"
        and (candidate / "install.json").is_file()
    ):
        return candidate
    from mos_eisley.app_install import default_root

    return default_root()


@contextlib.contextmanager
def active_client() -> Generator[None]:
    root = runtime_root()
    if root is None:
        yield
        return
    from mos_eisley.app_install import lock

    with lock(root, shared=True):
        yield


class SessionUpdates:
    def __init__(self, emit: Callable[[dict[str, object]], None]) -> None:
        self.emit = emit
        self.root = runtime_root()
        self.notified: str | None = None
        self.worker = asyncio.create_task(self.monitor())
        self.request: asyncio.Task[None] | None = None

    async def get(self, queue: ConversationInputQueue) -> ConversationInput:
        while True:
            item = await queue.get()
            if isinstance(item, str) and (
                item == "/update" or item.startswith("/update ")
            ):
                if self.request is None or self.request.done():
                    self.request = asyncio.create_task(self.command(item))
                else:
                    self.emit(
                        {
                            "type": "conversation.update",
                            "text": "An update check is already in progress.",
                        }
                    )
            else:
                return item

    async def close(self) -> None:
        self.worker.cancel()
        tasks = [self.worker]
        if self.request is not None:
            self.request.cancel()
            tasks.append(self.request)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def monitor(self) -> None:
        if self.root is None or not (sys.stdin.isatty() and sys.stdout.isatty()):
            return
        from mos_eisley.app_update import check, notice

        while True:
            try:
                result = await asyncio.to_thread(check, self.root)
                text = notice(result)
                if text and self.notified != result.get("latest"):
                    self.emit({"type": "conversation.update", "text": text})
                    self.notified = str(result["latest"])
            except (OSError, ValueError):
                pass
            await asyncio.sleep(15 * 60)

    async def command(self, text: str) -> None:
        from mos_eisley.app_install import default_root
        from mos_eisley.app_update import change_policy, check

        root = self.root or default_root()
        action = text.removeprefix("/update").strip()
        try:
            if action == "later":
                change_policy(root, "later")
                message = "Update reminder deferred for 24 hours."
            elif action == "skip":
                result = await asyncio.to_thread(check, root)
                target = result.get("latest")
                if not isinstance(target, str):
                    raise ValueError("No verified release is available to skip.")
                change_policy(root, "skip", target)
                message = (
                    f"Update notices for {target} skipped; "
                    "manual checks remain available."
                )
            elif action in {"now", "install"}:
                message = (
                    "Finish or cancel work and close sessions first. "
                    "Then run mos update; after installation, mos resume --last "
                    "explicitly resumes saved work. "
                    "No update is applied during a session."
                )
            elif action in {"", "check"}:
                result = await asyncio.to_thread(check, root, force=True)
                message = (
                    f"Update status: {result['status']}; "
                    f"installed {result['installed']}; "
                    f"available {result['latest']}. {result.get('notes') or ''}"
                )
            else:
                message = "Use /update, /update now, /update later or /update skip."
            self.emit({"type": "conversation.update", "text": message})
        except (OSError, ValueError) as error:
            self.emit(
                {
                    "type": "conversation.update",
                    "text": f"Unable to check updates: {error}",
                }
            )
