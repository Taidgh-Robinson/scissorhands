"""Work-item state and stable criterion identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkItem:
    """A Jira-style unit of work for a Scissorhands loop."""

    id: str
    title: str
    description: str
    definition_of_done: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    constraints: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()
    relevant_paths: tuple[str, ...] = ()
    non_goals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_work_item_id(self.id)

    def checklist(self) -> tuple[tuple[str, str], ...]:
        """Return stable IDs for every definition of done item and acceptance criterion."""
        return numbered_criteria("DoD", self.definition_of_done) + numbered_criteria(
            "AC", self.acceptance_criteria
        )


def validate_work_item_id(value: str) -> str:
    """Require one portable directory component for a work item ID."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]*", value
    ):
        raise ValueError(
            "'id' must contain only letters, digits, '-' or '_' and start with a letter or digit"
        )
    return value


def numbered_criteria(
    prefix: str, values: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    """Assign the same stable criterion IDs to prompts, status, and reports."""
    return tuple((f"{prefix}-{n}", value) for n, value in enumerate(values, start=1))
