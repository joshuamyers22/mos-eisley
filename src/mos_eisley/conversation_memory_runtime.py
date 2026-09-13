"""Trusted memory selection and recording updates for one terminal session."""

from collections.abc import Callable

from mos_eisley.conversation import RuntimeConversationController
from mos_eisley.conversation_memory import (
    ConversationMemory,
    MemoryRefreshError,
    MemoryStore,
)
from mos_eisley.conversation_memory_commands import (
    parse_memory_command,
    run_memory_command,
)
from mos_eisley.conversation_memory_forget import MemoryForget
from mos_eisley.conversation_memory_proposals import MemoryProposals
from mos_eisley.conversation_memory_replace import MemoryReplace
from mos_eisley.providers.agent_recorded import AgentCassette


class ConversationMemoryRuntime:
    def __init__(
        self,
        controller: RuntimeConversationController,
        store: MemoryStore,
        factory: Callable[[ConversationMemory | None], AgentCassette],
        *,
        ignore_memory: bool = False,
    ) -> None:
        self.controller = controller
        self.store = store
        self.forget = MemoryForget(store)
        self.replace = MemoryReplace(store)
        self.proposals = MemoryProposals(store, controller)
        self.factory = factory
        self.ignore_memory = ignore_memory
        self.builtin = controller.state.builtin_recording or (
            controller.cassette == factory(controller.state.memory)
        )

    def command(self, line: str) -> dict[str, object]:
        action = line.split(maxsplit=2)[:2]
        if action == ["/memory", "replace"]:
            self.forget.pending = None
            self.proposals.pending = None
        elif action == ["/memory", "forget"]:
            self.replace.pending = None
            self.proposals.pending = None
        elif action in (["/memory", "review-proposal"], ["/memory", "review-text"]):
            self.forget.pending = self.replace.pending = None
        receipt = self.proposals.command(line)
        if receipt is not None:
            return receipt
        receipt = self.replace.command(line)
        if receipt is not None:
            return receipt
        receipt = self.forget.command(line)
        if receipt is not None:
            return receipt
        if parse_memory_command(line).action != "show":
            self.forget.pending = self.replace.pending = None
            self.proposals.pending = None
        return run_memory_command(self.store, line)

    def check(self) -> None:
        if not self.ignore_memory:
            self.store.check(self.controller.state.memory)

    def refresh(
        self,
        disabled: bool,
        *,
        replacement: AgentCassette | None = None,
        snapshot_max_bytes: int | None = None,
    ) -> None:
        try:
            memory = None if disabled else self.store.load()
        except (OSError, ValueError):
            raise MemoryRefreshError(
                "Current memory could not be loaded. "
                "Correct its storage or use /memory off."
            ) from None
        builtin = self.builtin and replacement is None
        if replacement is None:
            if not builtin:
                raise MemoryRefreshError(
                    "Custom recordings need resume --refresh-memory "
                    "--refresh-cassette FILE."
                )
            fresh = self.factory(memory)
            consumed = self.controller.state.exchanges_consumed
            replacement = AgentCassette(
                exchanges=(
                    self.controller.cassette.exchanges[:consumed]
                    + fresh.exchanges[consumed:]
                )
            )
        self.controller.refresh_memory(
            memory,
            replacement,
            disabled=disabled,
            builtin=builtin,
            snapshot_max_bytes=snapshot_max_bytes,
        )
        self.builtin = builtin
        self.ignore_memory = disabled
