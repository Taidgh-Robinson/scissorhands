from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scissorhands.core.work_items import WorkItem, load_work_item


class WorkItemTests(TestCase):
    def test_rejects_missing_or_unsafe_id(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            base = (
                'title = "Example"\n'
                'description = "Do it."\n'
                'definition_of_done = ["Done."]\n'
                'acceptance_criteria = ["Works."]\n'
            )
            for identifier in (None, "../outside", "a/b", ".hidden", "bad space"):
                with self.subTest(identifier=identifier):
                    id_line = "" if identifier is None else f'id = "{identifier}"\n'
                    path.write_text(id_line + base, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "id"):
                        load_work_item(path)

    def test_loads_and_renders_structured_work_item(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            path.write_text(
                """
title = "Add export"
id = "EXPORT-1"
description = "Export records as JSON."
definition_of_done = ["Tests pass."]
acceptance_criteria = ["The output is valid JSON."]
constraints = ["Use the standard library."]
verification = ["python -m unittest"]
relevant_paths = ["src/export.py"]
non_goals = ["Do not add CSV export."]
""",
                encoding="utf-8",
            )

            work_item = load_work_item(path)

            self.assertEqual(work_item.title, "Add export")
            self.assertEqual(work_item.id, "EXPORT-1")
            prompt = work_item.as_prompt()
            self.assertIn("## Definition of done\n\n- DoD-1: Tests pass.", prompt)
            self.assertIn(
                "## Acceptance criteria\n\n- AC-1: The output is valid JSON.", prompt
            )
            self.assertIn("- `python -m unittest`", prompt)
            self.assertIn("## Relevant paths\n\n- `src/export.py`", prompt)
            self.assertIn("## Non-goals\n\n- Do not add CSV export.", prompt)
            self.assertLess(
                prompt.index("## Relevant paths"), prompt.index("## Definition of done")
            )

    def test_rejects_missing_required_fields(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            path.write_text(
                'id = "INCOMPLETE-1"\ntitle = "Incomplete"\n', encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "description"):
                load_work_item(path)

    def test_rejects_empty_acceptance_criteria(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            path.write_text(
                """
title = "Incomplete"
id = "INCOMPLETE-1"
description = "Missing outcomes."
definition_of_done = ["Tests pass."]
acceptance_criteria = []
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "acceptance_criteria"):
                load_work_item(path)

    def test_optional_sections_default_to_empty(self) -> None:
        work_item = WorkItem(
            id="SMALL-1",
            title="Small change",
            description="Make the change.",
            definition_of_done=("Tests pass.",),
            acceptance_criteria=("Behavior is observable.",),
        )

        prompt = work_item.as_prompt()

        self.assertNotIn("## Relevant paths", prompt)
        self.assertNotIn("## Constraints", prompt)
        self.assertNotIn("## Non-goals", prompt)
        self.assertNotIn("## Verification", prompt)

    def test_optional_sections_may_be_empty_arrays(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            path.write_text(
                """
title = "Small change"
id = "SMALL-1"
description = "Make the change."
definition_of_done = ["Tests pass."]
acceptance_criteria = ["Behavior is observable."]
constraints = []
verification = []
relevant_paths = []
non_goals = []
""",
                encoding="utf-8",
            )

            work_item = load_work_item(path)

            self.assertEqual(work_item.constraints, ())
            self.assertEqual(work_item.verification, ())
            self.assertEqual(work_item.relevant_paths, ())
            self.assertEqual(work_item.non_goals, ())

    def test_checklist_assigns_stable_ids(self) -> None:
        work_item = WorkItem(
            id="SMALL-1",
            title="Small change",
            description="Make the change.",
            definition_of_done=("Tests pass.", "Docs updated."),
            acceptance_criteria=("Behavior is observable.",),
        )

        self.assertEqual(
            work_item.checklist(),
            (
                ("DoD-1", "Tests pass."),
                ("DoD-2", "Docs updated."),
                ("AC-1", "Behavior is observable."),
            ),
        )
