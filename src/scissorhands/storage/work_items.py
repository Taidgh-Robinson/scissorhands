"""Load and validate work-item TOML files."""

import tomllib
from pathlib import Path

from scissorhands.core.work_items import WorkItem, validate_work_item_id


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
