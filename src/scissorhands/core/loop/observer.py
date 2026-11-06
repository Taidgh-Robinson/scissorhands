"""Optional notifications for interfaces that display live run activity."""

from pathlib import Path

from scissorhands.core.iteration import IterationRecord
from scissorhands.core.status import CriterionStatus
from scissorhands.core.verification import VerificationResult


class RunObserver:
    """Silent by default; override only the notifications an interface needs.

    Hooks are synchronous and should return promptly. Storage warnings can arrive
    from worker threads. Artifacts remain the durable source of truth.
    """

    def on_iteration_started(self, number: int, maximum: int, agent: str) -> None:
        """An agent iteration is about to start."""

    def on_output(self, text: str) -> None:
        """A decoded chunk of agent output has arrived."""

    def on_status(
        self, path: Path, statuses: tuple[CriterionStatus, ...] | None, *, updated: bool
    ) -> None:
        """The latest criterion claims have been read."""

    def on_verification(self, result: VerificationResult) -> None:
        """Harness verification has finished."""

    def on_iteration_finished(self, record: IterationRecord, log: Path) -> None:
        """The iteration receipt and run manifest have been saved."""

    def on_warning(self, message: str) -> None:
        """A nonfatal artifact or Git operation failed."""
