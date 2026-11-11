"""Load, validate, and render work-item TOML files."""

import tomllib
from pathlib import Path

from scissorhands.core.work_items import WorkItem, validate_work_item_id


def _required_text(data: dict[str, object], field: str, source: object) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: '{field}' must be a non-empty string")
    return value.strip()


def _string_list(
    data: dict[str, object], field: str, source: object, *, required: bool
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


def build_work_item(data: dict[str, object], *, source: object) -> WorkItem:
    """Validate a plain field mapping, shared by TOML loading and other callers.

    `source` only labels error messages; it need not be a path.
    """
    return WorkItem(
        id=validate_work_item_id(_required_text(data, "id", source)),
        title=_required_text(data, "title", source),
        description=_required_text(data, "description", source),
        definition_of_done=_string_list(
            data, "definition_of_done", source, required=True
        ),
        acceptance_criteria=_string_list(
            data, "acceptance_criteria", source, required=True
        ),
        constraints=_string_list(data, "constraints", source, required=False),
        verification=_string_list(data, "verification", source, required=False),
        relevant_paths=_string_list(data, "relevant_paths", source, required=False),
        non_goals=_string_list(data, "non_goals", source, required=False),
    )


def load_work_item(path: Path) -> WorkItem:
    """Load and validate a work item from a TOML file."""
    try:
        with path.open("rb") as source:
            data = tomllib.load(source)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path}: invalid TOML: {error}") from error

    return build_work_item(data, source=path)


def dump_work_item(work_item: WorkItem) -> str:
    """Render a work item as TOML that `load_work_item` reads back unchanged."""
    fields = (
        ("id", work_item.id),
        ("title", work_item.title),
        ("description", work_item.description),
        ("relevant_paths", work_item.relevant_paths),
        ("definition_of_done", work_item.definition_of_done),
        ("acceptance_criteria", work_item.acceptance_criteria),
        ("constraints", work_item.constraints),
        ("non_goals", work_item.non_goals),
        ("verification", work_item.verification),
    )
    lines = [f"{name} = {_toml_value(value)}" for name, value in fields]
    return "\n".join(lines) + "\n"


def _toml_value(value: str | tuple[str, ...]) -> str:
    if isinstance(value, str):
        return _toml_string(value)
    if not value:
        return "[]"
    items = ", ".join(_toml_string(item) for item in value)
    return f"[{items}]"


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'
