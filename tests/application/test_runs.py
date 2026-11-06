import asyncio
import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scissorhands.application import RunObserver, RunRequest, RunService

WORK_ITEM = """id = "SERVICE-1"
title = "Test the service"
description = "Run one loop."
definition_of_done = ["Tests pass."]
acceptance_criteria = ["The task is done."]
"""


class RunServiceTests(TestCase):
    def test_missing_or_file_root_is_rejected_before_preparing(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "file"
            file.write_text("not a directory")
            for invalid_root in (root / "missing", file):
                with (
                    self.subTest(root=invalid_root),
                    self.assertRaisesRegex(ValueError, "Project root"),
                ):
                    RunService(invalid_root).prepare(RunRequest())

    def test_preview_uses_root_and_does_not_create_run_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "WORK_ITEM.toml").write_text(WORK_ITEM, encoding="utf-8")
            (root / "custom.md").write_text(
                "Round $iteration: say $marker. Update $status_path.\n",
                encoding="utf-8",
            )
            service = RunService(root, find_executable=lambda _: "/bin/opencode")
            preview = service.preview(
                RunRequest(
                    agent="opencode",
                    model="test-model",
                    contract_path=Path("custom.md"),
                )
            )

            self.assertEqual(
                preview.command[:4], ("/bin/opencode", "run", "--model", "test-model")
            )
            self.assertFalse(preview.uses_stdin)
            self.assertIn("Round 1: say <promise>COMPLETE</promise>.", preview.prompt)
            self.assertIn("run-DRY-RUN", preview.prompt)
            self.assertNotIn("--auto", preview.command)
            self.assertFalse((root / ".scissorhands").exists())

    def test_run_uses_injected_invoker_and_returns_loop_result(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "WORK_ITEM.toml").write_text(WORK_ITEM, encoding="utf-8")
            calls = []

            def invoke(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                calls.append((command, prompt, cwd))
                (log.parent / "status.json").write_text(
                    json.dumps(
                        {
                            "DoD-1": {"met": True, "evidence": "Tests passed."},
                            "AC-1": {"met": True, "evidence": "Observed."},
                        }
                    ),
                    encoding="utf-8",
                )
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            service = RunService(
                root,
                invoke=invoke,
                find_executable=lambda _: "/bin/opencode",
            )
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                result = asyncio.run(
                    service.run(RunRequest(agent="opencode", max_iterations=2))
                )

            self.assertEqual(output.getvalue(), "")
            self.assertTrue(result.completed)
            self.assertEqual(result.iterations, 1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][2], root.resolve())
            self.assertIsNone(calls[0][1])
            self.assertTrue((result.run_dir / "report.md").is_file())

    def test_invalid_requests_are_rejected_before_a_run_is_created(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "WORK_ITEM.toml").write_text(WORK_ITEM, encoding="utf-8")
            service = RunService(root, find_executable=lambda _: None)
            for request, message in (
                (RunRequest(max_iterations=0), "max_iterations must be at least 1"),
                (
                    RunRequest(work_item_path=Path("missing.toml")),
                    "Work item does not exist",
                ),
                (RunRequest(agent="unknown"), "Unknown agent"),
                (RunRequest(agent="opencode"), "Agent executable not found"),
            ):
                with (
                    self.subTest(request=request),
                    self.assertRaisesRegex(ValueError, message),
                ):
                    service.prepare(request)
            self.assertFalse((root / ".scissorhands").exists())

    def test_observer_receives_run_activity_and_storage_warnings(self) -> None:
        events = []

        class RecordingObserver(RunObserver):
            def on_iteration_started(self, number, maximum, agent):
                events.append(("started", number))

            def on_status(self, path, statuses, *, updated):
                events.append(("status", updated))

            def on_iteration_finished(self, record, log):
                events.append(("finished", record.decision.outcome))

            def on_warning(self, message):
                events.append(("warning", message))

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "WORK_ITEM.toml").write_text(WORK_ITEM)

            def invoke(command, prompt, log, cwd):
                log.write_text("still working")
                return 0

            service = RunService(
                root,
                invoke=invoke,
                find_executable=lambda _: "agent",
                observer=RecordingObserver(),
            )
            with patch(
                "scissorhands.storage.runs.snapshot_worktree",
                side_effect=OSError("Git unavailable"),
            ):
                result = asyncio.run(
                    service.run(RunRequest(agent="opencode", max_iterations=1))
                )
            self.assertFalse(result.completed)
            self.assertEqual(
                [event[0] for event in events],
                ["warning", "started", "status", "finished"],
            )
            self.assertIn("Git unavailable", events[0][1])
            self.assertEqual(events[-1], ("finished", "iteration_limit"))
            self.assertTrue((result.run_dir / "report.json").is_file())
