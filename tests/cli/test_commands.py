import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import ANY, AsyncMock, patch

from scissorhands.application import RunPreview
from scissorhands.cli import main
from scissorhands.cli.reporting import TerminalReporter
from scissorhands.core.loop.models import LoopResult


class CliServiceTests(TestCase):
    def test_cli_streams_real_process_output_and_preserves_failure_exit_code(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "WORK_ITEM.toml").write_text("""id = "CLI-1"
title = "Exercise the CLI"
description = "Read a real subprocess result."
definition_of_done = ["Done"]
acceptance_criteria = ["Works"]
""")
            executable = root / "fake-agent"
            executable.write_text(
                f"#!{sys.executable}\nimport sys\nprint('agent output', flush=True)\nsys.exit(7)\n"
            )
            executable.chmod(0o755)
            output, errors = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                exit_code = main(
                    [
                        "--root",
                        str(root),
                        "--agent",
                        "opencode",
                        "--executable",
                        str(executable),
                        "--max-iterations",
                        "1",
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertIn("Scissorhands iteration 1/1", output.getvalue())
            self.assertIn("agent output", output.getvalue())
            self.assertIn("Agent command failed with exit code 7", errors.getvalue())
            log = root / ".scissorhands/CLI-1/run-0001/loop-0001/iteration-1.log"
            self.assertEqual(log.read_text(), "agent output\n")

    def test_root_is_passed_to_service_without_changing_working_directory(self) -> None:
        original = Path.cwd()
        with (
            patch("scissorhands.cli.commands.RunService") as service_type,
            redirect_stdout(StringIO()),
        ):
            service_type.return_value.preview.return_value = RunPreview(
                ("agent",), "prompt", True
            )
            self.assertEqual(main(["--root", "/tmp/other-project", "--dry-run"]), 0)
        service_type.assert_called_once_with(Path("/tmp/other-project"), observer=ANY)
        self.assertIsInstance(
            service_type.call_args.kwargs["observer"], TerminalReporter
        )
        self.assertEqual(Path.cwd(), original)

    def test_dry_run_calls_service_preview(self) -> None:
        preview = RunPreview(("opencode", "run", "full prompt"), "full prompt", False)
        output = StringIO()
        with (
            patch("scissorhands.cli.commands.RunService") as service_type,
            redirect_stdout(output),
        ):
            service_type.return_value.preview.return_value = preview
            exit_code = main(["--agent", "opencode", "--dry-run"])

        self.assertEqual(exit_code, 0)
        service_type.assert_called_once_with(Path.cwd(), observer=ANY)
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
                patch("scissorhands.cli.commands.RunService") as service_type,
            ):
                service_type.return_value.run = AsyncMock(return_value=result)
                with redirect_stdout(StringIO()):
                    exit_code = main(["--max-iterations", "2"])
                self.assertEqual(exit_code, expected)
                service_type.return_value.run.assert_called_once()
