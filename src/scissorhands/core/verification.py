"""Verification results and feedback for completion decisions."""

from dataclasses import dataclass

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
