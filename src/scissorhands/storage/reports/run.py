"""Write the human-readable run report."""

from pathlib import Path

from scissorhands.core.iteration import IterationRecord, run_outcome
from scissorhands.core.work_items import WorkItem
from scissorhands.storage.reports.formatting import (
    criterion_state,
    table_cell,
    verification_state,
)
from scissorhands.storage.reports.planning import objective_text, plan_section


def write_run_report(
    run_dir: Path, work_item: WorkItem, records: list[IterationRecord]
) -> None:
    """Summarize the completed invocation in Markdown."""
    final = records[-1]
    outcome = run_outcome(records)
    lines = [
        f"# {work_item.id}: {work_item.title}",
        "",
        f"Final outcome: **{outcome}** after {len(records)} loop(s).",
    ]
    if final.decision.rejection_reason:
        lines.append(f"Last rejection: {table_cell(final.decision.rejection_reason)}.")
    lines += _timeline_section(work_item, records)
    lines += plan_section(final)
    lines += _criteria_history(work_item, records)
    lines += _verification_history(work_item, records)
    lines += [
        "",
        "[Work item snapshot](work-item.json) · [Run settings](run.json) · [Machine-readable report](report.json)",
    ]
    if (run_dir / "changes.patch").exists():
        lines[-1] += " · [Full code changes](changes.patch)"
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _timeline_section(work_item: WorkItem, records: list[IterationRecord]) -> list[str]:
    lines = [
        "",
        "## Timeline",
        "",
        "| Loop | Selected objective (agent claim) | Outcome | Claimed met | Verification | Elapsed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        claimed = (
            sum(item.met is True for item in record.statuses or ())
            if record.status_updated and record.statuses is not None
            else "unknown"
        )
        verification = _verification_summary(record)
        elapsed = (
            f"{record.elapsed_seconds:.2f}s"
            if record.elapsed_seconds is not None
            else "unknown"
        )
        lines.append(
            f"| [Loop {record.iteration:04d}](loop-{record.iteration:04d}/iteration-{record.iteration}.md) "
            f"| {table_cell(objective_text(record))} "
            f"| {record.decision.outcome} | {claimed}/{len(work_item.checklist())} | {verification} "
            f"| {elapsed} |"
        )
    return lines


def _criteria_history(work_item: WorkItem, records: list[IterationRecord]) -> list[str]:
    lines = [
        "",
        "## Criteria history (agent claims)",
        "",
        "| ID | " + " | ".join(f"Loop {record.iteration}" for record in records) + " |",
        "| --- | " + " | ".join("---" for _ in records) + " |",
    ]
    for item_id, text in work_item.checklist():
        lines.append(
            f"| {table_cell(item_id + ': ' + text)} | "
            + " | ".join(criterion_state(record, item_id) for record in records)
            + " |"
        )
    return lines


def _verification_history(
    work_item: WorkItem, records: list[IterationRecord]
) -> list[str]:
    lines = []
    if work_item.verification:
        lines += [
            "",
            "## Verification history",
            "",
            "| Command | "
            + " | ".join(f"Loop {record.iteration}" for record in records)
            + " |",
            "| --- | " + " | ".join("---" for _ in records) + " |",
        ]
        for command in work_item.verification:
            lines.append(
                f"| {table_cell(command)} | "
                + " | ".join(verification_state(record, command) for record in records)
                + " |"
            )
    return lines


def _verification_summary(record: IterationRecord) -> str:
    if not record.verification_required:
        return "not configured"
    if record.verification is None:
        return "not run"
    results = record.verification.results
    passed = sum(result.passed for result in results)
    return f"{passed}/{len(results)} passed"
