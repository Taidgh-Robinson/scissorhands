from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scissorhands.core.status import CriterionStatus
from scissorhands.storage.agent_state import read_status

CHECKLIST = (("DoD-1", "Tests pass."), ("AC-1", "It works."))


class ReadStatusTests(TestCase):
    def test_reads_status_for_each_checklist_item(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(
                '{"DoD-1": {"met": true, "evidence": " Ran tests. "},'
                ' "AC-1": {"met": false}}',
                encoding="utf-8",
            )

            statuses = read_status(path, CHECKLIST)

        self.assertEqual(
            statuses,
            (
                CriterionStatus("DoD-1", "Tests pass.", True, "Ran tests."),
                CriterionStatus("AC-1", "It works.", False),
            ),
        )

    def test_missing_or_malformed_entries_are_unreported(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text('{"DoD-1": {"met": "yes"}}', encoding="utf-8")

            statuses = read_status(path, CHECKLIST)

        assert statuses is not None
        self.assertEqual([status.met for status in statuses], [None, None])

    def test_unusable_files_return_none(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            self.assertIsNone(read_status(path, CHECKLIST))

            path.write_text("not json", encoding="utf-8")
            self.assertIsNone(read_status(path, CHECKLIST))

            path.write_text("[]", encoding="utf-8")
            self.assertIsNone(read_status(path, CHECKLIST))
