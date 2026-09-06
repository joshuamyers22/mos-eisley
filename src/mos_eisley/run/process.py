"""Bounded host subprocess plumbing shared by launcher and detached cleanup."""

import os
import selectors
import subprocess
import tempfile
import time

MAX_WIRE_BYTES = 16_000_000


def docker_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key
        in (
            "PATH",
            "HOME",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        )
    }


def bounded_process(
    command: list[str],
    payload: bytes = b"",
    timeout: float = 30,
    limit: int = MAX_WIRE_BYTES,
) -> bytes:
    """Drain both pipes; terminate the client on limits or cancellation."""
    if len(payload) > MAX_WIRE_BYTES:
        raise ValueError("isolated input exceeds byte limit")
    with tempfile.TemporaryFile() as source:
        source.write(payload)
        source.seek(0)
        with (
            subprocess.Popen(
                command,
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=docker_environment(),
            ) as process,
            selectors.DefaultSelector() as selector,
        ):
            assert process.stdout is not None and process.stderr is not None
            streams = {process.stdout: bytearray(), process.stderr: bytearray()}
            for stream in streams:
                selector.register(stream, selectors.EVENT_READ)
            deadline = time.monotonic() + timeout
            try:
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError("isolated process deadline exceeded")
                    for key, _ in selector.select(min(remaining, 0.1)):
                        stream = (
                            process.stdout
                            if key.fileobj is process.stdout
                            else process.stderr
                        )
                        block = os.read(stream.fileno(), 65536)
                        if not block:
                            selector.unregister(stream)
                            continue
                        buffer = streams[stream]
                        cap = limit if stream is process.stdout else 65536
                        if len(buffer) + len(block) > cap:
                            raise ValueError(
                                "isolated process output exceeds byte limit"
                            )
                        buffer.extend(block)
                remaining = deadline - time.monotonic()
                if remaining <= 0 or process.wait(timeout=remaining) != 0:
                    raise ValueError("isolated process failed")
                return bytes(streams[process.stdout])
            except BaseException as error:
                process.kill()
                process.wait()
                if isinstance(error, subprocess.TimeoutExpired):
                    raise ValueError("isolated process deadline exceeded") from None
                raise
