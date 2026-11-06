"""Harness-run verification commands."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scissorhands.core.execution import stop_process

FEEDBACK_TAIL_LINES = 60


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The outcome of one verification command."""

    command: str
    return_code: int
    output: str

    @property
    def passed(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The outcome of every verification command after one iteration."""

    results: tuple[CommandResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def feedback(self, tail_lines: int = FEEDBACK_TAIL_LINES) -> str:
        """Summarize failing commands for the next iteration's prompt."""
        sections = []
        for result in self.results:
            if result.passed:
                continue
            heading = f"`{result.command}` exited with code {result.return_code}."
            lines = result.output.rstrip().splitlines()[-tail_lines:]
            if not lines:
                sections.append(f"{heading} It produced no output.")
                continue
            output = "\n".join(lines)
            sections.append(
                f"{heading} Last {len(lines)} line(s) of output:\n\n"
                f"```text\n{output}\n```"
            )
        return "\n\n".join(sections)


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
