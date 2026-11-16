"""Agent-reported implementation plans and one selected objective per loop."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from scissorhands.core.work_items import WorkItem

PLAN_FILE = "plan.json"
StepStatus = Literal["pending", "in_progress", "completed", "blocked"]


@dataclass(frozen=True, slots=True)
class PlanStep:
    id: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    status: StepStatus


@dataclass(frozen=True, slots=True)
class ImplementationPlan:
    schema_version: int
    iteration: int
    steps: tuple[PlanStep, ...]
    selected_step_id: str
    revision_reason: str
    handoff: str

    @property
    def selected_step(self) -> PlanStep:
        return next(step for step in self.steps if step.id == self.selected_step_id)

    @property
    def definition(self) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        """Compare structure independently of statuses and loop selection."""
        return tuple(
            (step.id, step.objective, step.acceptance_criteria) for step in self.steps
        )


def _text(data: dict, key: str, *, allow_empty: bool = False) -> str:
    value = data.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def parse_plan(data: object, work_item: WorkItem) -> ImplementationPlan:
    """Validate an agent plan without accessing the filesystem."""
    if not isinstance(data, dict):
        raise ValueError("plan must be a JSON object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("plan schema_version must be 1")
    if type(data.get("iteration")) is not int or data["iteration"] < 1:
        raise ValueError("plan iteration must be a positive integer")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("plan steps must be a non-empty array")
    known_criteria = {
        item_id for item_id, _ in work_item.checklist() if item_id.startswith("AC-")
    }
    steps: list[PlanStep] = []
    seen: set[str] = set()
    covered: set[str] = set()
    for entry in raw_steps:
        if not isinstance(entry, dict):
            raise ValueError("each plan step must be an object")
        step_id = _text(entry, "id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", step_id):
            raise ValueError("step id must contain only letters, digits, '-' or '_'")
        if step_id in seen:
            raise ValueError(f"duplicate step id: {step_id}")
        seen.add(step_id)
        criteria = entry.get("acceptance_criteria")
        if (
            not isinstance(criteria, list)
            or not criteria
            or any(not isinstance(item, str) for item in criteria)
        ):
            raise ValueError(
                f"{step_id}: acceptance_criteria must be a non-empty array of IDs"
            )
        if len(set(criteria)) != len(criteria) or not set(criteria) <= known_criteria:
            raise ValueError(
                f"{step_id}: acceptance_criteria must contain unique known AC IDs"
            )
        covered.update(criteria)
        status = entry.get("status")
        if status not in ("pending", "in_progress", "completed", "blocked"):
            raise ValueError(f"{step_id}: invalid step status")
        steps.append(
            PlanStep(step_id, _text(entry, "objective"), tuple(criteria), status)
        )
    if missing := known_criteria - covered:
        raise ValueError(
            f"plan does not cover acceptance criteria: {', '.join(sorted(missing))}"
        )
    selected = _text(data, "selected_step_id")
    if selected not in seen:
        raise ValueError("selected_step_id must identify exactly one existing step")
    if any(step.status == "in_progress" and step.id != selected for step in steps):
        raise ValueError("only the selected step may be in_progress")
    if next(step for step in steps if step.id == selected).status == "pending":
        raise ValueError("the selected step must be in_progress, completed, or blocked")
    return ImplementationPlan(
        1,
        data["iteration"],
        tuple(steps),
        selected,
        _text(data, "revision_reason", allow_empty=True),
        _text(data, "handoff"),
    )


def plan_revision_problem(
    plan: ImplementationPlan, previous: ImplementationPlan | None
) -> str | None:
    """Require a reason when a plan is created or its ordered steps change."""
    if (
        previous is None or plan.definition != previous.definition
    ) and not plan.revision_reason:
        return "revision_reason is required when creating or changing the plan"
    return None
