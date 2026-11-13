from copy import deepcopy
from dataclasses import replace
from unittest import TestCase

from scissorhands.core.planning import parse_plan, plan_revision_problem
from scissorhands.core.work_items import WorkItem

WORK_ITEM = WorkItem(
    "EXPORT",
    "Export data",
    "Add a streaming export.",
    ("Tests pass.",),
    ("Rows stream.", "The CLI exports."),
)
PLAN = {
    "schema_version": 1,
    "iteration": 1,
    "steps": [
        {
            "id": "STREAM",
            "objective": "Stream rows.",
            "acceptance_criteria": ["AC-1"],
            "status": "completed",
        },
        {
            "id": "CLI",
            "objective": "Connect the CLI.",
            "acceptance_criteria": ["AC-2"],
            "status": "pending",
        },
    ],
    "selected_step_id": "STREAM",
    "revision_reason": "Initial implementation plan.",
    "handoff": "Next connect the CLI.",
}


class PlanningTests(TestCase):
    def test_plan_selects_one_objective_and_preserves_criterion_links(self) -> None:
        plan = parse_plan(PLAN, WORK_ITEM)
        self.assertEqual(plan.selected_step.objective, "Stream rows.")
        self.assertEqual(plan.selected_step.acceptance_criteria, ("AC-1",))
        self.assertEqual(plan.steps[1].status, "pending")
        self.assertEqual(plan.handoff, "Next connect the CLI.")

    def test_invalid_plans_are_rejected(self) -> None:
        cases = [
            ({"schema_version": True}, "schema_version"),
            ({"schema_version": 2}, "schema_version"),
            ({"iteration": True}, "iteration"),
            ({"iteration": 0}, "iteration"),
            ({"steps": []}, "non-empty array"),
            ({"steps": [None]}, "must be an object"),
            ({"selected_step_id": ["STREAM", "CLI"]}, "selected_step_id"),
            ({"selected_step_id": "UNKNOWN"}, "exactly one existing step"),
            ({"handoff": "  "}, "handoff"),
        ]
        for changes, message in cases:
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, message),
            ):
                parse_plan({**PLAN, **changes}, WORK_ITEM)
        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_plan([], WORK_ITEM)

    def test_invalid_steps_and_multiple_active_objectives_are_rejected(self) -> None:
        cases = [
            (0, {"id": "CLI"}, "duplicate step"),
            (0, {"id": "../escape"}, "step id"),
            (0, {"objective": " "}, "objective"),
            (0, {"status": "done"}, "invalid step status"),
            (0, {"status": "pending"}, "selected step"),
            (1, {"status": "in_progress"}, "only the selected step"),
            (0, {"acceptance_criteria": []}, "non-empty array"),
            (0, {"acceptance_criteria": [True]}, "array of IDs"),
            (0, {"acceptance_criteria": ["AC-1", "AC-1"]}, "unique known AC"),
            (0, {"acceptance_criteria": ["AC-99"]}, "unique known AC"),
            (0, {"acceptance_criteria": ["DoD-1"]}, "unique known AC"),
            (1, {"acceptance_criteria": ["AC-1"]}, "does not cover.*AC-2"),
        ]
        for index, changes, message in cases:
            data = deepcopy(PLAN)
            data["steps"][index].update(changes)
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, message),
            ):
                parse_plan(data, WORK_ITEM)

    def test_initial_and_structural_revisions_need_a_reason(self) -> None:
        initial = parse_plan(PLAN, WORK_ITEM)
        self.assertIsNone(plan_revision_problem(initial, None))
        self.assertIn(
            "revision_reason",
            plan_revision_problem(replace(initial, revision_reason=""), None),
        )
        status_only = replace(
            initial,
            iteration=2,
            selected_step_id="CLI",
            steps=(initial.steps[0], replace(initial.steps[1], status="completed")),
            revision_reason="",
            handoff="No work remains.",
        )
        self.assertIsNone(plan_revision_problem(status_only, initial))
        structural_changes = [
            tuple(reversed(status_only.steps)),
            (
                replace(status_only.steps[0], objective="Stream bounded batches."),
                status_only.steps[1],
            ),
            (
                replace(status_only.steps[0], acceptance_criteria=("AC-1", "AC-2")),
                status_only.steps[1],
            ),
            (replace(status_only.steps[0], id="NEW"), status_only.steps[1]),
        ]
        for steps in structural_changes:
            revised = replace(status_only, steps=steps)
            self.assertIn("revision_reason", plan_revision_problem(revised, initial))
            self.assertIsNone(
                plan_revision_problem(
                    replace(
                        revised,
                        revision_reason="Repository discovery changed the plan.",
                    ),
                    initial,
                )
            )
