"""Read and carry forward bounded, contained implementation-plan snapshots."""

import json
from pathlib import Path

from scissorhands.core.planning import (
    ImplementationPlan,
    parse_plan,
    plan_revision_problem,
)
from scissorhands.core.work_items import WorkItem
from scissorhands.storage.artifacts import ReadWindow, read_artifact_file


def copy_plan(source: Path, destination: Path) -> None:
    """Carry usable JSON forward without following a file outside the run."""
    artifact = read_artifact_file(source, source.parent.parent.resolve(), ReadWindow())
    if artifact.state == "available":
        destination.write_text(
            json.dumps(artifact.data, indent=2) + "\n", encoding="utf-8"
        )


def read_plan(
    path: Path, work_item: WorkItem, previous: ImplementationPlan | None
) -> tuple[ImplementationPlan | None, str | None, bool]:
    artifact = read_artifact_file(path, path.parent.parent.resolve(), ReadWindow())
    if artifact.state != "available":
        return None, f"implementation plan is {artifact.state}", False
    try:
        plan = parse_plan(artifact.data, work_item)
    except ValueError as error:
        return None, f"invalid implementation plan: {error}", False
    revised = previous is None or plan.definition != previous.definition
    return plan, plan_revision_problem(plan, previous), revised
