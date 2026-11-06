import asyncio
import shlex
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scissorhands.core.loop.verification import run_verification
from scissorhands.core.verification import (
    CommandResult,
    VerificationResult,
)

PYTHON = shlex.quote(sys.executable)


class RunVerificationTests(TestCase):
    def test_reports_each_command_result(self) -> None:
        with TemporaryDirectory() as directory:
            result = asyncio.run(
                run_verification(
                    [
                        f"{PYTHON} -c \"print('ok')\"",
                        f"{PYTHON} -c \"import sys; print('boom'); sys.exit(3)\"",
                    ],
                    Path(directory),
                )
            )

        self.assertFalse(result.passed)
        self.assertEqual([r.return_code for r in result.results], [0, 3])
        self.assertEqual(result.results[0].output, "ok\n")

    def test_runs_in_the_given_directory(self) -> None:
        with TemporaryDirectory() as directory:
            (Path(directory) / "marker.txt").write_text("here", encoding="utf-8")
            result = asyncio.run(
                run_verification(
                    [f"{PYTHON} -c \"print(open('marker.txt').read())\""],
                    Path(directory),
                )
            )

        self.assertTrue(result.passed)
        self.assertIn("here", result.results[0].output)


class FeedbackTests(TestCase):
    def test_feedback_lists_only_failing_commands(self) -> None:
        verification = VerificationResult(
            (
                CommandResult("lint", 0, "clean\n"),
                CommandResult("tests", 1, "FAILED test_thing\n"),
            )
        )

        feedback = verification.feedback()

        self.assertNotIn("lint", feedback)
        self.assertIn("`tests` exited with code 1.", feedback)
        self.assertIn("FAILED test_thing", feedback)

    def test_feedback_keeps_only_the_output_tail(self) -> None:
        output = "\n".join(f"line {n}" for n in range(1, 11))
        verification = VerificationResult((CommandResult("tests", 1, output),))

        feedback = verification.feedback(tail_lines=3)

        self.assertIn("Last 3 line(s)", feedback)
        self.assertIn("line 10", feedback)
        self.assertNotIn("line 7", feedback)

    def test_feedback_handles_silent_failures(self) -> None:
        verification = VerificationResult((CommandResult("tests", 2, ""),))

        self.assertIn("It produced no output.", verification.feedback())
