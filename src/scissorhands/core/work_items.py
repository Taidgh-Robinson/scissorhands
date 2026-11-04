"""Structured work-item loading and prompt rendering."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


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
        return _numbered("DoD", self.definition_of_done) + _numbered(
            "AC", self.acceptance_criteria
        )

    def as_prompt(self) -> str:
        """Render the work item as an explicit agent-facing prompt."""
        sections = [
            f"# Work item: {self.title}",
            f"## Description\n\n{self.description}",
        ]
        if self.relevant_paths:
            sections.append(
                _render_list("Relevant paths", self.relevant_paths, code=True)
            )
        sections += [
            _render_list(
                "Definition of done",
                tuple(_labelled(_numbered("DoD", self.definition_of_done))),
            ),
            _render_list(
                "Acceptance criteria",
                tuple(_labelled(_numbered("AC", self.acceptance_criteria))),
            ),
        ]
        if self.constraints:
            sections.append(_render_list("Constraints", self.constraints))
        if self.non_goals:
            sections.append(_render_list("Non-goals", self.non_goals))
        if self.verification:
            sections.append(_render_list("Verification", self.verification, code=True))
        return "\n\n".join(sections)


def validate_work_item_id(value: str) -> str:
    """Require one portable directory component for a work item ID."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]*", value
    ):
        raise ValueError(
            "'id' must contain only letters, digits, '-' or '_' and start with a letter or digit"
        )
    return value


def _numbered(prefix: str, values: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple((f"{prefix}-{n}", value) for n, value in enumerate(values, start=1))


def _labelled(items: tuple[tuple[str, str], ...]) -> list[str]:
    return [f"{item_id}: {text}" for item_id, text in items]


def _render_list(title: str, values: tuple[str, ...], *, code: bool = False) -> str:
    items = (f"`{value}`" if code else value for value in values)
    return f"## {title}\n\n" + "\n".join(f"- {item}" for item in items)


def _required_text(data: dict[str, object], field: str, source: Path) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: '{field}' must be a non-empty string")
    return value.strip()


def _string_list(
    data: dict[str, object], field: str, source: Path, *, required: bool
) -> tuple[str, ...]:
    value = data.get(field)
    if value is None and not required:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{source}: '{field}' must be an array of strings")
    if required and not value:
        raise ValueError(f"{source}: '{field}' must be a non-empty array of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{source}: '{field}' must contain only non-empty strings")
    return tuple(item.strip() for item in value)


def load_work_item(path: Path) -> WorkItem:
    """Load and validate a work item from a TOML file."""
    try:
        with path.open("rb") as source:
            data = tomllib.load(source)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path}: invalid TOML: {error}") from error

    return WorkItem(
        id=validate_work_item_id(_required_text(data, "id", path)),
        title=_required_text(data, "title", path),
        description=_required_text(data, "description", path),
        definition_of_done=_string_list(
            data, "definition_of_done", path, required=True
        ),
        acceptance_criteria=_string_list(
            data, "acceptance_criteria", path, required=True
        ),
        constraints=_string_list(data, "constraints", path, required=False),
        verification=_string_list(data, "verification", path, required=False),
        relevant_paths=_string_list(data, "relevant_paths", path, required=False),
        non_goals=_string_list(data, "non_goals", path, required=False),
    )
