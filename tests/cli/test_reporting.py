from unittest import TestCase

from scissorhands.cli.reporting import format_status
from scissorhands.core.status import CriterionStatus

CHECKLIST = (("DoD-1", "Tests pass."), ("AC-1", "It works."))


class FormatStatusTests(TestCase):
    def test_renders_a_checklist(self) -> None:
        rendered = format_status(
            (
                CriterionStatus("DoD-1", "Tests pass.", True, "Ran tests."),
                CriterionStatus("AC-1", "It works.", False),
                CriterionStatus("AC-2", "It is fast.", None),
            )
        )

        self.assertEqual(
            rendered,
            "[x] DoD-1: Tests pass.\n"
            "      Ran tests.\n"
            "[ ] AC-1: It works.\n"
            "[?] AC-2: It is fast.",
        )
