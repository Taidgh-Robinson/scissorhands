"""Present the selected objective and its agent-reported plan snapshot."""

from scissorhands.core.iteration import IterationRecord
from scissorhands.storage.reports.formatting import table_cell


def objective_text(record: IterationRecord) -> str:
    if record.plan is None:
        return "unknown"
    step = record.plan.selected_step
    text = f"{step.id}: {step.objective} ({step.status})"
    if record.planning_problem:
        text += " [stale or invalid plan]"
    return text


def plan_section(record: IterationRecord) -> list[str]:
    lines = ["", "## Implementation plan (agent claims)", ""]
    if problem := record.planning_problem:
        lines.append(f"Plan problem: {table_cell(problem)}.")
    if record.plan is None:
        lines.append("No readable implementation plan.")
        return lines
    plan = record.plan
    lines += ["", f"Selected objective: **{table_cell(objective_text(record))}**."]
    if record.plan_revised:
        lines += [
            "",
            f"Plan creation/revision reason: {table_cell(plan.revision_reason) or 'missing'}",
        ]
    lines += [
        "",
        "| Step | Intended outcome | Acceptance criteria | Claimed status |",
        "| --- | --- | --- | --- |",
    ]
    for step in plan.steps:
        lines.append(
            f"| {step.id} | {table_cell(step.objective)} | "
            f"{', '.join(step.acceptance_criteria)} | {step.status} |"
        )
    lines += ["", f"Handoff: {table_cell(plan.handoff)}"]
    return lines
