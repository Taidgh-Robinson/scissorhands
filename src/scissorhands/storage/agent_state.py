"""Read agent-written status and progress without interpreting completion."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scissorhands.core.status import CriterionStatus


@dataclass(frozen=True, slots=True)
class AgentState:
    """Timestamps and criterion claims observed after an agent invocation."""

    status_modified_ns: int | None
    progress_modified_ns: int | None
    statuses: tuple[CriterionStatus, ...] | None


def read_modification_times(
    status: Path, progress: Path
) -> tuple[int | None, int | None]:
    return modified_ns(status), modified_ns(progress)


def read_agent_state(
    status: Path, progress: Path, checklist: Sequence[tuple[str, str]]
) -> AgentState:
    status_time, progress_time = read_modification_times(status, progress)
    return AgentState(status_time, progress_time, read_status(status, checklist))


def read_status(
    path: Path, checklist: Sequence[tuple[str, str]]
) -> tuple[CriterionStatus, ...] | None:
    """Return status for every checklist item, or None when the file is unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    statuses = []
    for item_id, text in checklist:
        entry = data.get(item_id)
        met: bool | None = None
        evidence = ""
        if isinstance(entry, dict):
            if isinstance(entry.get("met"), bool):
                met = entry["met"]
            if isinstance(entry.get("evidence"), str):
                evidence = entry["evidence"].strip()
        statuses.append(CriterionStatus(item_id, text, met, evidence))
    return tuple(statuses)


def modified_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def read_progress(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None
