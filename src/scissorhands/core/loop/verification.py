"""Execute the work item's verification commands asynchronously."""

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

from scissorhands.core.loop.processes import stop_process
from scissorhands.core.verification import CommandResult, VerificationResult


async def run_verification(commands: Sequence[str], cwd: Path) -> VerificationResult:
    """Run each command through the shell without blocking the event loop."""
    results = []
    for command in commands:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        try:
            output, _ = await process.communicate()
        except asyncio.CancelledError:
            await stop_process(process)
            raise
        results.append(
            CommandResult(
                command, process.returncode, output.decode("utf-8", errors="replace")
            )
        )
    return VerificationResult(tuple(results))
