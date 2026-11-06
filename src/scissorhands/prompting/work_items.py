"""Render structured work items as agent-facing instructions."""

from scissorhands.core.work_items import WorkItem, numbered_criteria


def render_work_item(work_item: WorkItem) -> str:
    """Render the work item as an explicit agent-facing prompt."""
    sections = [
        f"# Work item: {work_item.title}",
        f"## Description\n\n{work_item.description}",
    ]
    if work_item.relevant_paths:
        sections.append(
            _render_list("Relevant paths", work_item.relevant_paths, code=True)
        )
    sections += [
        _render_list(
            "Definition of done",
            tuple(_labelled(numbered_criteria("DoD", work_item.definition_of_done))),
        ),
        _render_list(
            "Acceptance criteria",
            tuple(_labelled(numbered_criteria("AC", work_item.acceptance_criteria))),
        ),
    ]
    if work_item.constraints:
        sections.append(_render_list("Constraints", work_item.constraints))
    if work_item.non_goals:
        sections.append(_render_list("Non-goals", work_item.non_goals))
    if work_item.verification:
        sections.append(_render_list("Verification", work_item.verification, code=True))
    return "\n\n".join(sections)


def _labelled(items: tuple[tuple[str, str], ...]) -> list[str]:
    return [f"{item_id}: {text}" for item_id, text in items]


def _render_list(title: str, values: tuple[str, ...], *, code: bool = False) -> str:
    items = (f"`{value}`" if code else value for value in values)
    return f"## {title}\n\n" + "\n".join(f"- {item}" for item in items)
