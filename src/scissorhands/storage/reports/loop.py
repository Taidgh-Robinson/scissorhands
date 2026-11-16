"""Write the human-readable loop report."""

from pathlib import Path

from scissorhands.core.iteration import IterationRecord
from scissorhands.core.status import STATUS_FILE
from scissorhands.core.work_items import WorkItem
from scissorhands.storage.reports.formatting import (
    criterion_state,
    table_cell,
    verification_state,
)
from scissorhands.storage.reports.planning import plan_section


def write_loop_report(
    loop_dir: Path,
    work_item: WorkItem,
    record: IterationRecord,
    previous: IterationRecord | None,
) -> None:
    """Describe one loop's claims, verification, and stop decision."""
    number = record.iteration
    decision = record.decision
    lines = [
        f"# Loop {number:04d}",
        "",
        f"Agent: {table_cell(record.agent)}; exit code: {record.agent_exit_code}.",
        f"Outcome: **{decision.outcome}**. Completion marker claimed: {'yes' if record.marker_claimed else 'no'}.",
    ]
    if record.elapsed_seconds is not None:
        lines.append(f"Elapsed: {record.elapsed_seconds:.2f} seconds.")
    if decision.rejection_reason:
        lines.append(f"Completion rejected: {table_cell(decision.rejection_reason)}.")
    lines += plan_section(record)
    lines += _criteria_section(work_item, record, previous)
    lines += _verification_section(work_item, record, previous)
    lines += _progress_section(loop_dir, record)
    (loop_dir / f"iteration-{number}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _criteria_section(
    work_item: WorkItem, record: IterationRecord, previous: IterationRecord | None
) -> list[str]:
    lines = [
        "",
        "## Criteria (agent claims)",
        "",
        "| ID | Previous | Current | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for item_id, _ in work_item.checklist():
        item = next(
            (item for item in record.statuses or () if item.id == item_id), None
        )
        evidence = item.evidence if item is not None and record.status_updated else ""
        lines.append(
            f"| {item_id} | {criterion_state(previous, item_id)} | "
            f"{criterion_state(record, item_id)} | {table_cell(evidence)} |"
        )
    return lines


def _verification_section(
    work_item: WorkItem, record: IterationRecord, previous: IterationRecord | None
) -> list[str]:
    lines = ["", "## Verification (harness observations)", ""]
    if not work_item.verification:
        lines.append("Not configured.")
    else:
        lines += [
            "| Command | Previous | Current | Output |",
            "| --- | --- | --- | --- |",
        ]
        for index, command in enumerate(work_item.verification, 1):
            output = (
                f"[verification-{index}.log](verification-{index}.log)"
                if record.verification is not None
                else ""
            )
            lines.append(
                f"| {table_cell(command)} | {verification_state(previous, command)} | "
                f"{verification_state(record, command)} | {output} |"
            )
    return lines


def _progress_section(loop_dir: Path, record: IterationRecord) -> list[str]:
    number = record.iteration
    lines = [
        "",
        "## Agent progress note",
        "",
        "Updated this loop."
        if record.progress_updated
        else "Carried forward without an update.",
        "",
        record.progress or "No readable progress note.",
        "",
        f"Artifacts: [prompt](prompt.md), [receipt](iteration-{number}.json), "
        f"[agent output](iteration-{number}.log), [progress](progress.md).",
    ]
    if (loop_dir / STATUS_FILE).exists():
        lines[-1] += " [Status](status.json)."
    if (loop_dir / "changes.patch").exists():
        lines[-1] += " [Code changes](changes.patch)."
    if (loop_dir / "plan.json").exists():
        lines[-1] += " [Implementation plan](plan.json)."
    return lines
