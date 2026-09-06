"""One bounded request/reply over owned subprocess pipes, with no listener."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from contextlib import suppress

from mos_eisley.run.process import MAX_WIRE_BYTES, docker_environment

ExchangeHandler = Callable[[bytes], Awaitable[bytes]]
CLAIM_LIMIT = 1024


async def _frame(reader: asyncio.StreamReader, limit: int) -> bytes:
    result = await reader.readuntil(b"\n")
    if len(result) > limit + 1:
        raise ValueError("broker frame exceeds byte limit")
    return result[:-1]


async def _stderr(reader: asyncio.StreamReader) -> bytes:
    size = 0
    while block := await reader.read(4096):
        size += len(block)
        if size > 65536:
            raise ValueError("broker stderr exceeds byte limit")
    return b""


async def _discard(reader: asyncio.StreamReader) -> None:
    while await reader.read(65536):
        pass


async def _conversation(
    process: asyncio.subprocess.Process, offer: bytes, handler: ExchangeHandler
) -> bytes:
    assert process.stdin is not None and process.stdout is not None
    writer, reader = process.stdin, process.stdout
    writer.write(offer + b"\n")
    await writer.drain()
    claim = await _frame(reader, CLAIM_LIMIT)
    # Any byte/EOF before the host reply is a protocol violation/disconnect.
    # Keep watching while provider work is pending so cancellation reaches spend
    # admission. A remote call already sent can still incur its reserved charge.
    early = asyncio.create_task(reader.read(1))
    response: asyncio.Future[bytes] | None = None
    try:
        await asyncio.sleep(0)
        if early.done():
            raise ValueError("broker worker sent early output or disconnected")
        response = asyncio.ensure_future(handler(claim))
        done, _ = await asyncio.wait(
            (early, response), return_when=asyncio.FIRST_COMPLETED
        )
        if early in done:
            raise ValueError("broker worker sent early output or disconnected")
        reply = response.result()
        if len(reply) > MAX_WIRE_BYTES or b"\n" in reply:
            raise ValueError("broker reply exceeds framing bounds")
    finally:
        pending = [early] if response is None else [early, response]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    writer.write(reply + b"\n")
    await writer.drain()
    writer.close()
    result = await _frame(reader, CLAIM_LIMIT)
    if await reader.read(1):
        raise ValueError("broker worker sent extra output")
    if await process.wait() != 0:
        raise ValueError("broker worker failed")
    return result


async def bounded_exchange(
    command: list[str],
    offer: bytes,
    handler: ExchangeHandler,
    timeout: float = 30,
) -> bytes:
    """A single cooperative deadline covers launch, handler, reply and worker exit.

    stdout frames are limited to 1 KiB; replies to 16 MB; stderr to 64 KiB.
    The caller owns container removal: killing a Docker client is insufficient.
    """
    if (
        len(offer) > CLAIM_LIMIT
        or b"\n" in offer
        or not math.isfinite(timeout)
        or not 0 < timeout <= 60
    ):
        raise ValueError("invalid broker exchange bounds")
    process: asyncio.subprocess.Process | None = None
    tasks: list[asyncio.Task[bytes]] = []
    try:
        async with asyncio.timeout(timeout):
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=docker_environment(),
                limit=CLAIM_LIMIT + 1,
            )
            assert process.stderr is not None
            exchange = asyncio.create_task(_conversation(process, offer, handler))
            errors = asyncio.create_task(_stderr(process.stderr))
            tasks = [exchange, errors]
            await asyncio.gather(*tasks)
            return exchange.result()
    except (
        ValueError,
        OSError,
        TimeoutError,
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,
    ):
        # Never include wire data, bearer grants, or child stderr in public errors.
        raise ValueError("broker exchange failed") from None
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            # Drain after killing: wait() alone can deadlock with paused readers.
            assert process.stdout is not None and process.stderr is not None
            async with asyncio.timeout(3):
                await asyncio.gather(
                    _discard(process.stdout), _discard(process.stderr), process.wait()
                )
