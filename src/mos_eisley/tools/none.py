"""Dispatcher that advertises and executes no tools."""

from mos_eisley.core.protocol import ToolCallBlock, ToolDefinition, ToolResultBlock


class NoToolsDispatcher:
    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return ()

    async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
        raise ValueError("no tools are configured")
