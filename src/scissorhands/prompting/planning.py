"""The implementation-plan contract shared by default and custom prompts."""

import json

from scissorhands.core.work_items import WorkItem


def render_planning(
    work_item: WorkItem, iteration: int, plan_path: str, feedback: str | None
) -> str:
    criteria = [
        item_id for item_id, _ in work_item.checklist() if item_id.startswith("AC-")
    ]
    example = {
        "schema_version": 1,
        "iteration": iteration,
        "steps": [
            {
                "id": "STEP-1",
                "objective": "Replace with one small, concrete, verifiable outcome.",
                "acceptance_criteria": criteria,
                "status": "in_progress",
            }
        ],
        "selected_step_id": "STEP-1",
        "revision_reason": "Initial implementation plan.",
        "handoff": "Work has just started; update with the result and clearest next step before exiting.",
    }
    recovery = ""
    if feedback:
        recovery = f"\nPrevious loop's planning feedback: {feedback}\nRepair the plan in this iteration.\n"
    return f"""## Implementation plan and loop objective

Read `{plan_path}` if it exists; it is copied from the previous loop. On the first loop,
inspect the repository and create a small implementation plan covering every acceptance
criterion. Split the work into steps with stable IDs and one concrete intended outcome each.
The JSON below shows the shape; replace its example step with the actual implementation steps.

Before changing implementation code, write `{plan_path}` with `iteration` set to {iteration}
and select exactly ONE step using `selected_step_id`. State its intended outcome in `objective`.
Keep implementation and related tests/docs focused on that objective this loop. A step may span
multiple loops; select it again if unfinished. When verification feedback reports failures,
select or add a repair step before starting unrelated work. On the final loop, select a small
finish-or-wrap-up objective that fits the remaining budget.

```json
{json.dumps(example, indent=2)}
```

Use only `pending`, `in_progress`, `completed`, or `blocked` for step status. Only the selected
step may be `in_progress`, and the selected step cannot remain `pending`. Link each step to
one or more AC IDs shown above, and keep every acceptance criterion covered by the plan.
Preserve IDs for the same steps; do not recycle IDs for unrelated work. Keep completed steps
in the plan. If discovery requires adding, removing, reordering, or changing step definitions,
record what changed and why in `revision_reason`; it may be empty when only status/selection
changes. A new plan requires a reason. If you change this loop's objective, explain that change.

Before exiting, update the selected step's status and `handoff` with what happened, any blocker,
and the clearest next step (or explicitly state that no work remains). Also update progress and
criteria status as the iteration contract requires. Plan status is an agent claim, not independent
verification. Completing a step does not complete the work item. The harness accepts completion
only with a fresh, valid plan for this iteration, every plan step `completed`, and the existing
criteria and verification gates satisfied. It records the final plan; it cannot prove that you
wrote the objective before editing code.
{recovery}"""
