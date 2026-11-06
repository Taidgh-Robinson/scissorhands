import asyncio
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from scissorhands.cli import main
from scissorhands.core.run_service import RunPreview, RunRequest, RunService
from scissorhands.core.runner import LoopResult

WORK_ITEM = """id = "SERVICE-1"
title = "Test the service"
description = "Run one loop."
definition_of_done = ["Tests pass."]
acceptance_criteria = ["The task is done."]
"""


class RunServiceTests(TestCase):
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
            result = asyncio.run(
                service.run(RunRequest(agent="opencode", max_iterations=2))
            )

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
                (RunRequest(max_iterations=0), "--max-iterations must be at least 1"),
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


class CliServiceTests(TestCase):
    def test_dry_run_calls_service_preview(self) -> None:
        preview = RunPreview(("opencode", "run", "full prompt"), "full prompt", False)
        output = StringIO()
        with (
            patch("scissorhands.cli.RunService") as service_type,
            redirect_stdout(output),
        ):
            service_type.return_value.preview.return_value = preview
            exit_code = main(["--agent", "opencode", "--dry-run"])

        self.assertEqual(exit_code, 0)
        service_type.return_value.preview.assert_called_once()
        service_type.return_value.run.assert_not_called()
        self.assertEqual(
            service_type.return_value.preview.call_args.args[0].agent, "opencode"
        )
        self.assertIn("opencode run '<PROMPT>'", output.getvalue())
        self.assertIn("full prompt", output.getvalue())

    def test_run_calls_service_and_preserves_exit_codes(self) -> None:
        for result, expected in (
            (LoopResult(True, 1, Path("/tmp/run")), 0),
            (LoopResult(False, 1, Path("/tmp/run"), failed=True), 1),
            (LoopResult(False, 2, Path("/tmp/run")), 2),
        ):
            with (
                self.subTest(result=result),
                patch("scissorhands.cli.RunService") as service_type,
            ):
                service_type.return_value.run = AsyncMock(return_value=result)
                with redirect_stdout(StringIO()):
                    exit_code = main(["--max-iterations", "2"])
                self.assertEqual(exit_code, expected)
                service_type.return_value.run.assert_called_once()
