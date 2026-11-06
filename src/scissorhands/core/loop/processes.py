"""Invoke agents and stream their output to a log."""

from __future__ import annotations

import asyncio
import codecs
import os
import signal
from collections.abc import Callable
from pathlib import Path


async def stop_process(process: asyncio.subprocess.Process) -> None:
    """Stop a subprocess and its children before releasing a cancelled task."""
    if process.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        await process.wait()
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        await process.wait()


async def run_command(
    command: list[str],
    prompt: str | None,
    log_path: Path,
    cwd: Path,
    *,
    on_output: Callable[[str], None] | None = None,
) -> int:
    """Save combined output and optionally notify a caller as chunks arrive."""
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE
        if prompt is not None
        else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )

    async def send_prompt() -> None:
        if prompt is not None:
            assert process.stdin is not None
            process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()

    writer = asyncio.create_task(send_prompt())
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    try:
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8") as log:
            while chunk := await process.stdout.read(8192):
                output = decoder.decode(chunk)
                if on_output is not None:
                    on_output(output)
                await asyncio.to_thread(log.write, output)
                await asyncio.to_thread(log.flush)
            tail = decoder.decode(b"", final=True)
            if tail:
                if on_output is not None:
                    on_output(tail)
                await asyncio.to_thread(log.write, tail)
        await writer
        return await process.wait()
    except BaseException:
        await stop_process(process)
        writer.cancel()
        await asyncio.gather(writer, return_exceptions=True)
        raise
