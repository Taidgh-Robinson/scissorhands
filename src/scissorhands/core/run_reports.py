"""Human-readable reports derived from harness iteration records."""

from __future__ import annotations

import json
from pathlib import Path

from scissorhands.core.iteration import IterationRecord
from scissorhands.core.status import STATUS_FILE
from scissorhands.core.work_items import WorkItem


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _criterion_state(record: IterationRecord | None, item_id: str) -> str:
    if record is None:
        return "unknown"
    if not record.status_updated:
        return "stale"
    if record.statuses is None:
        return "unreadable"
    item = next((item for item in record.statuses if item.id == item_id), None)
    if item is None or item.met is None:
        return "unreported"
    return "met" if item.met else "unmet"


def _verification_state(record: IterationRecord | None, command: str) -> str:
    if record is None:
        return "unknown"
    if record.verification is None:
        return "not run" if record.verification_required else "not configured"
    item = next(
        (item for item in record.verification.results if item.command == command), None
    )
    if item is None:
        return "not run"
    return "passed" if item.passed else f"failed (exit {item.return_code})"


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
        f"Agent: {_cell(record.agent)}; exit code: {record.agent_exit_code}.",
        f"Outcome: **{decision.outcome}**. Completion marker claimed: {'yes' if record.marker_claimed else 'no'}.",
    ]
    if record.elapsed_seconds is not None:
        lines.append(f"Elapsed: {record.elapsed_seconds:.2f} seconds.")
    if decision.rejection_reason:
        lines.append(f"Completion rejected: {_cell(decision.rejection_reason)}.")
    lines += [
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
            f"| {item_id} | {_criterion_state(previous, item_id)} | "
            f"{_criterion_state(record, item_id)} | {_cell(evidence)} |"
        )
    lines += ["", "## Verification (harness observations)", ""]
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
                f"| {_cell(command)} | {_verification_state(previous, command)} | "
                f"{_verification_state(record, command)} | {output} |"
            )
    lines += [
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
    (loop_dir / f"iteration-{number}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_run_report(
    run_dir: Path, work_item: WorkItem, records: list[IterationRecord]
) -> None:
    """Summarize the completed invocation and retain a small JSON index."""
    final = records[-1]
    outcome = (
        final.decision.outcome
        if final.decision.accepted or final.decision.outcome == "agent_failed"
        else "iteration_limit"
    )
    timeline = [
        {
            "loop": record.iteration,
            "outcome": record.decision.outcome,
            "rejection_reason": record.decision.rejection_reason,
            "receipt": f"loop-{record.iteration:04d}/iteration-{record.iteration}.json",
            "report": f"loop-{record.iteration:04d}/iteration-{record.iteration}.md",
        }
        for record in records
    ]
    summary = {
        "schema_version": 1,
        "work_item_id": work_item.id,
        "outcome": outcome,
        "loops": timeline,
    }
    (run_dir / "report.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"# {work_item.id}: {work_item.title}",
        "",
        f"Final outcome: **{outcome}** after {len(records)} loop(s).",
    ]
    if final.decision.rejection_reason:
        lines.append(f"Last rejection: {_cell(final.decision.rejection_reason)}.")
    lines += [
        "",
        "## Timeline",
        "",
        "| Loop | Outcome | Claimed met | Verification | Elapsed |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        claimed = (
            sum(item.met is True for item in record.statuses or ())
            if record.status_updated and record.statuses is not None
            else "unknown"
        )
        verification = (
            "not configured"
            if not record.verification_required
            else "not run"
            if record.verification is None
            else f"{sum(item.passed for item in record.verification.results)}/{len(record.verification.results)} passed"
        )
        elapsed = (
            f"{record.elapsed_seconds:.2f}s"
            if record.elapsed_seconds is not None
            else "unknown"
        )
        lines.append(
            f"| [Loop {record.iteration:04d}](loop-{record.iteration:04d}/iteration-{record.iteration}.md) "
            f"| {record.decision.outcome} | {claimed}/{len(work_item.checklist())} | {verification} "
            f"| {elapsed} |"
        )
    lines += [
        "",
        "## Criteria history (agent claims)",
        "",
        "| ID | " + " | ".join(f"Loop {record.iteration}" for record in records) + " |",
        "| --- | " + " | ".join("---" for _ in records) + " |",
    ]
    for item_id, text in work_item.checklist():
        lines.append(
            f"| {_cell(item_id + ': ' + text)} | "
            + " | ".join(_criterion_state(record, item_id) for record in records)
            + " |"
        )
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
                f"| {_cell(command)} | "
                + " | ".join(_verification_state(record, command) for record in records)
                + " |"
            )
    lines += [
        "",
        "[Work item snapshot](work-item.json) · [Run settings](run.json) · [Machine-readable report](report.json)",
    ]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
