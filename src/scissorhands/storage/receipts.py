"""Serialize iteration records using the existing receipt format."""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from scissorhands.core.iteration import IterationRecord


def receipt_data(record: IterationRecord) -> dict[str, object]:
    decision = record.decision
    return {
        "recorded_at": datetime.now(UTC).isoformat(),
        "iteration": record.iteration,
        "agent": record.agent,
        "agent_exit_code": record.agent_exit_code,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "elapsed_seconds": record.elapsed_seconds,
        "agent_elapsed_seconds": record.agent_elapsed_seconds,
        "verification_elapsed_seconds": record.verification_elapsed_seconds,
        "git_before_tree": record.git_before_tree,
        "git_after_tree": record.git_after_tree,
        "outcome": decision.outcome,
        "rejection_reason": decision.rejection_reason,
        "progress_updated": record.progress_updated,
        "progress": record.progress,
        "status_updated": record.status_updated,
        "status_readable": record.statuses is not None,
        "criteria": [asdict(item) for item in record.statuses or ()],
        "verification": _verification_data(record),
        "completion_marker_claimed": record.marker_claimed,
        "completion_accepted": decision.accepted,
        "plan_required": record.plan_required,
        "plan_updated": record.plan_updated,
        "plan_error": record.plan_error,
        "plan_revised": record.plan_revised,
        "plan": asdict(record.plan) if record.plan is not None else None,
    }


def _verification_data(record: IterationRecord) -> dict[str, object]:
    verification = record.verification
    commands = (
        []
        if verification is None
        else [
            {
                "command": result.command,
                "return_code": result.return_code,
                "passed": result.passed,
            }
            for result in verification.results
        ]
    )
    return {
        "required": record.verification_required,
        "passed": verification.passed if verification is not None else None,
        "commands": commands,
    }


def write_iteration_receipt(path: Path, record: IterationRecord) -> None:
    """Persist one iteration without altering prior receipts."""
    path.write_text(json.dumps(receipt_data(record), indent=2) + "\n", encoding="utf-8")
