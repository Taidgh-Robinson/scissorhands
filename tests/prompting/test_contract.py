from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scissorhands.core.work_items import WorkItem
from scissorhands.prompting.compose import compose_prompt
from scissorhands.prompting.contract import (
    default_contract,
    load_contract,
    render_contract,
    validate_contract,
)

WORK_ITEM = WorkItem(
    id="WORK-ITEM",
    title="Build the thing",
    description="Build the requested thing.",
    definition_of_done=("Tests pass.",),
    acceptance_criteria=("The thing works.",),
)


class ContractTests(TestCase):
    def test_default_contract_is_valid(self) -> None:
        validate_contract(default_contract(), "default")

    def test_rejects_unknown_placeholders(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown placeholder.*iteraton"):
            validate_contract("$marker $iteraton", "custom")

    def test_rejects_templates_without_the_marker(self) -> None:
        with self.assertRaisesRegex(ValueError, r"must include \$marker"):
            validate_contract("Iteration $iteration", "custom")

    def test_rejects_stray_dollar_signs(self) -> None:
        with self.assertRaisesRegex(ValueError, r"\$\$"):
            validate_contract("$marker costs $5", "custom")

    def test_literal_dollars_may_be_escaped(self) -> None:
        validate_contract("$marker costs $$5", "custom")
        self.assertEqual(render_contract("costs $$5"), "costs $5")

    def test_load_contract_reports_missing_files(self) -> None:
        with (
            TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "cannot read contract"),
        ):
            load_contract(Path(directory) / "missing.md")

    def test_custom_contract_replaces_the_default(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "contract.md"
            path.write_text(
                "## Custom\n\nRound $iteration/$max_iterations. Say $marker.\n",
                encoding="utf-8",
            )

            prompt = compose_prompt(
                WORK_ITEM, 2, "DONE", max_iterations=4, contract=load_contract(path)
            )

        self.assertIn("## Custom\n\nRound 2/4. Say DONE.", prompt)
        self.assertNotIn("Scissorhands iteration contract", prompt)
        self.assertTrue(prompt.startswith("# Work item: Build the thing"))
