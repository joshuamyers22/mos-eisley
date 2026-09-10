"""Trusted memory selection and recording updates for one terminal session."""

from collections.abc import Callable

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_memory import (
    ConversationMemory,
    MemoryRefreshError,
    MemoryStore,
)
from mos_eisley.providers.agent_recorded import AgentCassette


class ConversationMemoryRuntime:
    def __init__(
        self,
        controller: ConversationController,
        store: MemoryStore,
        factory: Callable[[ConversationMemory | None], AgentCassette],
        *,
        ignore_memory: bool = False,
    ) -> None:
        self.controller = controller
        self.store = store
        self.factory = factory
        self.ignore_memory = ignore_memory
        self.builtin = controller.state.builtin_recording or (
            controller.cassette == factory(controller.state.memory)
        )

    def check(self) -> None:
        if not self.ignore_memory:
            self.store.check(self.controller.state.memory)

    def refresh(
        self, disabled: bool, *, replacement: AgentCassette | None = None
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
            memory, replacement, disabled=disabled, builtin=builtin
        )
        self.builtin = builtin
        self.ignore_memory = disabled
