"""Iteration observations and deterministic completion decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scissorhands.core.planning import ImplementationPlan
from scissorhands.core.status import CriterionStatus
from scissorhands.core.verification import VerificationResult

Outcome = Literal[
    "agent_failed",
    "verification_failed",
    "criteria_rejected",
    "plan_rejected",
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
    plan: ImplementationPlan | None = None
    plan_updated: bool = False
    plan_error: str | None = None
    plan_revised: bool = False
    plan_required: bool = False

    @property
    def decision(self) -> CompletionDecision:
        return evaluate_completion(self)

    @property
    def verification_feedback(self) -> str | None:
        if self.verification is not None and not self.verification.passed:
            return self.verification.feedback()
        return None

    @property
    def planning_problem(self) -> str | None:
        """Explain missing, stale, or invalid plans independently of completion."""
        if self.plan_error:
            return self.plan_error
        if not self.plan_updated:
            return "implementation plan was not updated this iteration"
        if self.plan is None:
            return "implementation plan was not readable"
        if self.plan.iteration != self.iteration:
            return f"implementation plan must describe iteration {self.iteration}"
        return None

    @property
    def planning_feedback(self) -> str | None:
        if self.plan_required:
            if problem := self.planning_problem:
                return problem
            if self.marker_claimed:
                return unfinished_plan_problem(self)
        return None


def unfinished_plan_problem(record: IterationRecord) -> str | None:
    if record.plan is not None:
        unfinished = [
            step.id for step in record.plan.steps if step.status != "completed"
        ]
        if unfinished:
            return f"implementation plan has unfinished steps: {', '.join(unfinished)}"
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
        if record.plan_required:
            problem = record.planning_problem or unfinished_plan_problem(record)
            if problem is not None:
                return CompletionDecision("plan_rejected", problem)
        return CompletionDecision("completed")
    return CompletionDecision(
        "iteration_limit" if record.final_iteration else "continuing"
    )


def run_outcome(records: list[IterationRecord]) -> str:
    """Describe a finished run using the final iteration's completion decision."""
    final = records[-1]
    return (
        final.decision.outcome
        if final.decision.accepted or final.decision.outcome == "agent_failed"
        else "iteration_limit"
    )
