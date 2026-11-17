"""Publish the active loop's latest phase for readers in other processes."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

Phase = Literal["preparing", "agent", "assessing", "verifying", "finalizing"]


class LoopActivity:
    def __init__(
        self,
        run_dir: Path,
        loop: int,
        command_count: int,
        on_warning: Callable[[str], None],
    ) -> None:
        self.path = run_dir / "activity.json"
        self.loop = loop
        self.command_count = command_count
        self.on_warning = on_warning
        self.phase_started_at = ""

    async def set_phase(self, phase: Phase) -> None:
        self.phase_started_at = datetime.now(UTC).isoformat()
        await self._publish(phase, None)

    async def command_started(self, index: int, command: str) -> None:
        await self._publish(
            "verifying",
            {
                "index": index,
                "total": self.command_count,
                "command": command,
                "started_at": datetime.now(UTC).isoformat(),
            },
        )

    async def _publish(self, phase: Phase, verification: dict | None) -> None:
        snapshot = {
            "loop": self.loop,
            "phase": phase,
            "phase_started_at": self.phase_started_at,
            "verification": verification,
        }
        # A cancelled thread await does not stop a rename already in progress.
        # Finish it before cleanup so a late write cannot resurrect the activity.
        write = asyncio.create_task(asyncio.to_thread(self._replace, snapshot))
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            await write
            raise

    def _replace(self, snapshot: dict) -> None:
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete_on_close=False
            ) as temp:
                json.dump(snapshot, temp)
                temp.close()
                Path(temp.name).replace(self.path)
        except OSError as error:
            self.on_warning(f"Could not write loop activity: {error}")


@asynccontextmanager
async def track_loop_activity(
    run_dir: Path, loop: int, command_count: int, on_warning: Callable[[str], None]
) -> AsyncIterator[LoopActivity]:
    activity = LoopActivity(run_dir, loop, command_count, on_warning)
    try:
        await activity.set_phase("preparing")
        yield activity
    finally:
        try:
            await asyncio.to_thread(activity.path.unlink, missing_ok=True)
        except OSError as error:
            on_warning(f"Could not clear loop activity: {error}")
