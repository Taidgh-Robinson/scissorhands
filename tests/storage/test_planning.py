from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scissorhands.core.work_items import WorkItem
from scissorhands.storage.artifacts import MAX_JSON_BYTES
from scissorhands.storage.planning import copy_plan, read_plan

WORK_ITEM = WorkItem("TASK", "Build", "Build it.", ("Tests pass.",), ("Works.",))


class PlanStorageTests(TestCase):
    def test_missing_malformed_oversized_and_external_plans_are_explicit(self) -> None:
        with TemporaryDirectory() as directory:
            run = Path(directory) / "run-0001"
            loop = run / "loop-0001"
            loop.mkdir(parents=True)
            path = loop / "plan.json"
            plan, error, revised = read_plan(path, WORK_ITEM, None)
            self.assertIsNone(plan)
            self.assertEqual(error, "implementation plan is missing")
            self.assertFalse(revised)
            path.write_bytes(b"\xff")
            self.assertEqual(
                read_plan(path, WORK_ITEM, None)[1], "implementation plan is invalid"
            )
            path.write_text("x" * (MAX_JSON_BYTES + 1))
            self.assertEqual(
                read_plan(path, WORK_ITEM, None)[1], "implementation plan is too_large"
            )
            external = Path(directory) / "external.json"
            external.write_text('{"secret": "outside this run"}')
            path.unlink()
            path.symlink_to(external)
            self.assertEqual(
                read_plan(path, WORK_ITEM, None)[1], "implementation plan is unsafe"
            )
            next_loop = run / "loop-0002"
            next_loop.mkdir()
            copy_plan(path, next_loop / "plan.json")
            self.assertFalse((next_loop / "plan.json").exists())

    def test_invalid_json_is_preserved_in_its_loop_and_not_carried_forward(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            run = Path(directory)
            previous = run / "loop-0001"
            current = run / "loop-0002"
            previous.mkdir()
            current.mkdir()
            source = previous / "plan.json"
            source.write_text("partial JSON")
            copy_plan(source, current / "plan.json")
            self.assertEqual(source.read_text(), "partial JSON")
            self.assertFalse((current / "plan.json").exists())
