"""Atomically persist the run lifecycle and completed-loop timeline."""

import json
from datetime import UTC, datetime
from pathlib import Path

from scissorhands.core.iteration import IterationRecord, run_outcome
from scissorhands.core.work_items import WorkItem


def write_run_manifest(
    run_dir: Path,
    work_item: WorkItem,
    records: list[IterationRecord],
    started_at: str,
    *,
    finished: bool = False,
    cancelled: bool = False,
    queued: bool = False,
) -> None:
    """Atomically save the latest known run state, including interrupted runs."""
    now = datetime.now(UTC).isoformat()
    state, outcome = _run_state(
        records, finished=finished, cancelled=cancelled, queued=queued
    )
    summary = {
        "schema_version": 2,
        "run_id": run_dir.name,
        "work_item_id": work_item.id,
        "state": state,
        "outcome": outcome,
        "started_at": started_at,
        "updated_at": now,
        "finished_at": now if finished or cancelled else None,
        "loops": [_timeline_entry(record) for record in records],
    }
    temporary = run_dir / "report.json.tmp"
    temporary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    temporary.replace(run_dir / "report.json")


def _run_state(
    records: list[IterationRecord], *, finished: bool, cancelled: bool, queued: bool
) -> tuple[str, str | None]:
    if cancelled:
        return "cancelled", "cancelled"
    if finished:
        return "finished", run_outcome(records)
    if queued:
        return "queued", None
    return "running", None


def _timeline_entry(record: IterationRecord) -> dict[str, object]:
    return {
        "loop": record.iteration,
        "outcome": record.decision.outcome,
        "rejection_reason": record.decision.rejection_reason,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "elapsed_seconds": record.elapsed_seconds,
        "agent_elapsed_seconds": record.agent_elapsed_seconds,
        "verification_elapsed_seconds": record.verification_elapsed_seconds,
        "git_before_tree": record.git_before_tree,
        "git_after_tree": record.git_after_tree,
        "receipt": f"loop-{record.iteration:04d}/iteration-{record.iteration}.json",
        "report": f"loop-{record.iteration:04d}/iteration-{record.iteration}.md",
        "objective": (
            {
                "step_id": record.plan.selected_step.id,
                "intended_outcome": record.plan.selected_step.objective,
                "acceptance_criteria": list(
                    record.plan.selected_step.acceptance_criteria
                ),
                "claimed_status": record.plan.selected_step.status,
            }
            if record.plan is not None
            else None
        ),
        "plan_updated": record.plan_updated,
        "plan_problem": record.planning_problem if record.plan_required else None,
        "plan_revised": record.plan_revised,
    }
