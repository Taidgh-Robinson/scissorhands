"""Terminal presentation of iteration observations and decisions."""

import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from scissorhands.application.models import RunPreview
from scissorhands.core.iteration import IterationRecord
from scissorhands.core.loop.models import LoopResult
from scissorhands.core.loop.observer import RunObserver
from scissorhands.core.status import CriterionStatus
from scissorhands.core.verification import VerificationResult


def print_preview(preview: RunPreview) -> None:
    """Display the command separately from the potentially long prompt argument."""
    display_command = preview.command
    if not preview.uses_stdin:
        display_command = (*preview.command[:-1], "<PROMPT>")
    print("Command:")
    print(shlex.join(display_command))
    print("\nPrompt:\n")
    print(preview.prompt)


def report_run_result(result: LoopResult) -> int:
    """Print the final summary and return the CLI's established exit code."""
    if result.completed:
        print(
            f"\nScissorhands completed after {result.iterations} iteration(s). Logs: {result.run_dir}"
        )
        return 0
    if result.failed:
        return 1
    print(f"\nIteration limit reached without completion. Logs: {result.run_dir}")
    return 2


class TerminalReporter(RunObserver):
    """Render backend notifications using the CLI's existing terminal format."""

    def on_iteration_started(self, number: int, maximum: int, agent: str) -> None:
        print(f"\n=== Scissorhands iteration {number}/{maximum} ({agent}) ===")

    def on_output(self, text: str) -> None:
        print(text, end="", flush=True)

    def on_status(
        self, path: Path, statuses: tuple[CriterionStatus, ...] | None, *, updated: bool
    ) -> None:
        report_status(path, statuses, updated=updated)

    def on_verification(self, result: VerificationResult) -> None:
        report_verification(result)

    def on_iteration_finished(self, record: IterationRecord, log: Path) -> None:
        report_iteration(record, log)

    def on_warning(self, message: str) -> None:
        print(message, file=sys.stderr)


def report_status(
    path: Path, statuses: tuple[CriterionStatus, ...] | None, *, updated: bool
) -> None:
    print("\n--- Criteria status ---")
    if statuses is None:
        print(f"No readable status in {path}.")
        return
    if not updated:
        print("(not updated this iteration)")
    print(format_status(statuses))


def report_verification(verification: VerificationResult) -> None:
    print("\n--- Verification ---")
    for result in verification.results:
        status = "PASS" if result.passed else f"FAIL (exit {result.return_code})"
        print(f"{status}: {result.command}")
    if not verification.passed:
        print(verification.feedback(), file=sys.stderr)


def report_iteration(record: IterationRecord, log: Path) -> None:
    decision = record.decision
    if record.agent_exit_code != 0:
        print(
            f"Agent command failed with exit code {record.agent_exit_code}. Log: {log}",
            file=sys.stderr,
        )
    elif record.marker_claimed and decision.rejection_reason is not None:
        print(
            f"Ignoring the completion marker because {decision.rejection_reason}.",
            file=sys.stderr,
        )


def format_status(statuses: Sequence[CriterionStatus]) -> str:
    """Render statuses as a terminal checklist."""
    marks = {True: "x", False: " ", None: "?"}
    lines = []
    for status in statuses:
        lines.append(f"[{marks[status.met]}] {status.id}: {status.text}")
        if status.evidence:
            lines.append(f"      {status.evidence}")
    return "\n".join(lines)
