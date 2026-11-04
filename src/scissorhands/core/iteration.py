"""Iteration observations and deterministic completion decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scissorhands.core.status import CriterionStatus
from scissorhands.core.verification import VerificationResult

Outcome = Literal[
    "agent_failed",
    "verification_failed",
    "criteria_rejected",
    "completed",
    "iteration_limit",
    "continuing",
]


@dataclass(frozen=True, slots=True)
class CompletionDecision:
    outcome: Outcome
    rejection_reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.outcome == "completed"


@dataclass(frozen=True, slots=True)
class IterationRecord:
    iteration: int
    agent: str
    agent_exit_code: int
    statuses: tuple[CriterionStatus, ...] | None
    status_updated: bool
    progress: str | None
    progress_updated: bool
    verification: VerificationResult | None
    verification_required: bool
    marker_claimed: bool
    final_iteration: bool
    elapsed_seconds: float | None = None
    started_at: str | None = None
    finished_at: str | None = None
    agent_elapsed_seconds: float | None = None
    verification_elapsed_seconds: float | None = None
    git_before_tree: str | None = None
    git_after_tree: str | None = None

    @property
    def decision(self) -> CompletionDecision:
        return evaluate_completion(self)

    @property
    def verification_feedback(self) -> str | None:
        if self.verification is not None and not self.verification.passed:
            return self.verification.feedback()
        return None


def criteria_status_problem(record: IterationRecord) -> str | None:
    """Explain why the observed status cannot support completion."""
    if not record.status_updated:
        return "criteria status was not updated this iteration"
    if record.statuses is None:
        return "criteria status was not readable"
    unmet = [item.id for item in record.statuses if item.met is not True]
    if unmet:
        return f"not every criterion was met: {', '.join(unmet)}"
    missing_evidence = [item.id for item in record.statuses if not item.evidence]
    if missing_evidence:
        return f"criteria are missing evidence: {', '.join(missing_evidence)}"
    return None


def evaluate_completion(record: IterationRecord) -> CompletionDecision:
    """Apply the gates in priority order without reading files or printing."""
    if record.agent_exit_code != 0:
        return CompletionDecision("agent_failed")
    if record.verification is not None and not record.verification.passed:
        return CompletionDecision("verification_failed", "verification failed")
    if record.marker_claimed:
        problem = criteria_status_problem(record)
        if problem is not None:
            return CompletionDecision("criteria_rejected", problem)
        return CompletionDecision("completed")
    return CompletionDecision(
        "iteration_limit" if record.final_iteration else "continuing"
    )
