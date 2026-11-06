import asyncio
import json
import shlex
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from scissorhands.application import RunRequest, RunService
from scissorhands.core.loop.processes import run_command
from scissorhands.core.loop.verification import run_verification

WORK_ITEM = """id = "ASYNC-1"
title = "Test async runs"
description = "Run one loop."
definition_of_done = ["Tests pass."]
acceptance_criteria = ["The task is done."]
"""


class AsyncRunTests(IsolatedAsyncioTestCase):
    async def test_agent_output_streams_and_event_loop_remains_responsive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "agent.log"
            command = [
                sys.executable,
                "-u",
                "-c",
                "import time; print('first', flush=True); time.sleep(.2); print('second', flush=True)",
            ]
            chunks = []
            terminal = StringIO()
            with redirect_stdout(terminal), redirect_stderr(terminal):
                task = asyncio.create_task(
                    run_command(command, None, log, root, on_output=chunks.append)
                )
                await asyncio.wait_for(asyncio.sleep(0.02), timeout=0.1)
                self.assertFalse(task.done())
                self.assertEqual(await task, 0)
            self.assertEqual(terminal.getvalue(), "")
            self.assertEqual("".join(chunks), "first\nsecond\n")
            self.assertEqual(log.read_text(), "first\nsecond\n")

    async def test_reservation_precedes_execution_and_cancellation_is_durable(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "WORK_ITEM.toml").write_text(WORK_ITEM, encoding="utf-8")
            entered = asyncio.Event()

            async def invoke(command, prompt, log, cwd):
                entered.set()
                return await run_command(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    None,
                    log,
                    cwd,
                )

            service = RunService(
                root, invoke=invoke, find_executable=lambda _: sys.executable
            )
            config, paths = await service.reserve(RunRequest(agent="opencode"))
            self.assertEqual(paths.run_dir.name, "run-0001")
            self.assertTrue((paths.run_dir / "report.json").is_file())
            self.assertEqual(
                json.loads((paths.run_dir / "report.json").read_text())["state"],
                "queued",
            )
            task = asyncio.create_task(service.run_reserved(config, paths))
            await asyncio.wait_for(entered.wait(), timeout=2)
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)
            manifest = json.loads((paths.run_dir / "report.json").read_text())
            self.assertEqual(manifest["state"], "cancelled")
            self.assertEqual(manifest["outcome"], "cancelled")
            self.assertIsNotNone(manifest["finished_at"])

    async def test_verification_can_be_cancelled(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            command = f"{shlex.quote(sys.executable)} -c 'import time; time.sleep(30)'"
            task = asyncio.create_task(run_verification([command], root))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)
