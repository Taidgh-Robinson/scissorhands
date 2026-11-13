import asyncio
import json
import os
from contextlib import redirect_stdout
from dataclasses import asdict
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scissorhands.application import RunRequest, RunService
from scissorhands.storage.paths import UnsafeArtifactPath
from scissorhands.storage.repository import RunRepository


class RunRepositoryTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repository = RunRepository(self.root)
        self.run = self.root / ".scissorhands" / "TASK-1" / "run-0001"
        self.loop = self.run / "loop-0001"
        self.loop.mkdir(parents=True)

    def write_json(self, path: Path, data: object) -> None:
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_projects_are_isolated_and_queries_do_not_write(self) -> None:
        other = self.root / "other-project"
        other_run = other / ".scissorhands" / "TASK-1" / "run-0001"
        other_run.mkdir(parents=True)
        self.write_json(
            self.run / "report.json", {"state": "finished", "outcome": "completed"}
        )
        self.write_json(other_run / "report.json", {"state": "running"})
        before = sorted(str(path) for path in self.root.rglob("*"))

        self.assertEqual(self.repository.list_work_items(), ("TASK-1",))
        self.assertEqual(self.repository.list_runs()[0].outcome, "completed")
        self.assertEqual(RunRepository(other).list_runs()[0].state, "running")
        self.assertEqual(sorted(str(path) for path in self.root.rglob("*")), before)

    def test_missing_storage_is_empty_but_missing_project_is_an_error(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        repository = RunRepository(empty)
        self.assertEqual(repository.list_work_items(), ())
        self.assertEqual(repository.list_runs(), ())
        self.assertFalse((empty / ".scissorhands").exists())
        with self.assertRaises(FileNotFoundError):
            RunRepository(empty / "missing").list_runs()
        with self.assertRaises(FileNotFoundError):
            repository.read_run("TASK-1", "run-0001")

    def test_damaged_runs_remain_listable_in_numeric_order(self) -> None:
        for number, content in (
            (2, "{"),
            (10, "[]"),
            (11, "\ufffd"),
            (12, '{"state": []}'),
        ):
            run = self.run.parent / f"run-{number:04d}"
            run.mkdir()
            (run / "report.json").write_text(content, encoding="utf-8")
        (self.run.parent / "unrelated").mkdir()
        (self.run.parent / "run-0003").write_text("not a directory")
        summaries = self.repository.list_runs("TASK-1")
        self.assertEqual(
            [item.run_id for item in summaries],
            [
                "run-0001",
                "run-0002",
                "run-0010",
                "run-0011",
                "run-0012",
            ],
        )
        self.assertEqual(
            [item.manifest_state for item in summaries],
            [
                "missing",
                "invalid",
                "invalid",
                "invalid",
                "available",
            ],
        )
        self.assertTrue(all(item.state == "unknown" for item in summaries))

    def test_run_and_loop_details_preserve_receipts_and_discover_partial_loops(
        self,
    ) -> None:
        # The directory identity wins over IDs or paths supplied by a manifest.
        manifest = {
            "state": "running",
            "run_id": "other",
            "loops": [{"receipt": "../../secret"}],
        }
        receipt = {
            "criteria": [{"met": True}],
            "completion_accepted": False,
            "outcome": "continue",
        }
        self.write_json(self.run / "report.json", manifest)
        self.write_json(self.loop / "iteration-1.json", receipt)
        (self.run / "loop-0002").mkdir()
        (self.run / "loop-junk").mkdir()
        detail = self.repository.read_run("TASK-1", "run-0001")
        self.assertEqual(detail.summary.run_id, "run-0001")
        self.assertEqual(detail.manifest.data, manifest)
        self.assertEqual(detail.settings.state, "missing")
        self.assertEqual(detail.work_item.state, "missing")
        self.assertEqual(detail.loops, (1, 2))
        self.assertEqual(
            self.repository.read_loop("TASK-1", "run-0001", 1).receipt.data, receipt
        )
        self.assertEqual(
            self.repository.read_loop("TASK-1", "run-0001", 2).receipt.state, "missing"
        )
        json.dumps(asdict(detail))

    def test_text_windows_tails_and_growing_logs_are_bounded(self) -> None:
        log = self.loop / "iteration-1.log"
        log.write_bytes(b"0123456789")
        window = self.repository.read_artifact(
            "TASK-1", "run-0001", "agent_output", loop=1, offset=2, limit=4
        )
        self.assertEqual(
            (window.data, window.offset, window.bytes_read, window.total_bytes),
            ("2345", 2, 4, 10),
        )
        self.assertTrue(window.truncated)
        with log.open("ab") as source:
            source.write(b"abcdef")
        tail = self.repository.read_artifact(
            "TASK-1", "run-0001", "agent_output", loop=1, tail=True, limit=4
        )
        self.assertEqual((tail.data, tail.offset, tail.total_bytes), ("cdef", 12, 16))
        end = self.repository.read_artifact(
            "TASK-1", "run-0001", "agent_output", loop=1, offset=100
        )
        self.assertEqual((end.data, end.offset), ("", 16))

    def test_all_known_artifact_names_and_missing_files(self) -> None:
        for kind, name in {
            "manifest": "report.json",
            "settings": "run.json",
            "work_item": "work-item.json",
            "work_item_toml": "work-item.toml",
            "report": "report.md",
            "patch": "changes.patch",
        }.items():
            with self.subTest(kind=kind):
                (self.run / name).write_text("{}" if name.endswith(".json") else name)
                self.assertEqual(
                    self.repository.read_artifact("TASK-1", "run-0001", kind).state,
                    "available",
                )
        for kind, name in {
            "receipt": "iteration-1.json",
            "report": "iteration-1.md",
            "agent_output": "iteration-1.log",
            "final_message": "iteration-1.final.txt",
            "status": "status.json",
            "plan": "plan.json",
            "progress": "progress.md",
            "prompt": "prompt.md",
            "patch": "changes.patch",
            "verification_output": "verification-2.log",
        }.items():
            with self.subTest(kind=kind):
                (self.loop / name).write_text("{}" if name.endswith(".json") else name)
                kwargs = {"verification": 2} if kind == "verification_output" else {}
                result = self.repository.read_artifact(
                    "TASK-1", "run-0001", kind, loop=1, **kwargs
                )
                self.assertEqual(result.state, "available")
        self.assertEqual(
            self.repository.read_artifact(
                "TASK-1", "run-0001", "verification_output", loop=1, verification=3
            ).state,
            "missing",
        )

    def test_json_limits_invalid_encoding_and_nonregular_files(self) -> None:
        path = self.run / "report.json"
        path.write_bytes(b'{"large":"0123456789"}')
        with patch("scissorhands.storage.artifacts.MAX_JSON_BYTES", 8):
            self.assertEqual(self.repository.list_runs()[0].manifest_state, "too_large")
        path.write_bytes(b"\xff")
        self.assertEqual(self.repository.list_runs()[0].manifest_state, "invalid")
        (self.loop / "progress.md").mkdir()
        self.assertEqual(
            self.repository.read_artifact(
                "TASK-1", "run-0001", "progress", loop=1
            ).state,
            "unavailable",
        )
        os.mkfifo(self.loop / "iteration-1.log")
        self.assertEqual(
            self.repository.read_artifact(
                "TASK-1", "run-0001", "agent_output", loop=1
            ).state,
            "unavailable",
        )

    def test_rejects_traversal_arbitrary_files_and_invalid_windows(self) -> None:
        for item, run in (
            ("..", "run-0001"),
            ("/tmp", "run-0001"),
            ("TASK-1", "../run-0001"),
            ("TASK-1", "/tmp"),
        ):
            with self.subTest(item=item, run=run), self.assertRaises(ValueError):
                self.repository.read_run(item, run)
        for kind, kwargs in (
            ("../../secret", {}),
            ("report", {"loop": 0}),
            ("report", {"loop": True}),
            ("report", {"offset": -1}),
            ("report", {"limit": 0}),
            ("report", {"limit": 2**30}),
            ("report", {"offset": 1, "tail": True}),
            ("manifest", {"tail": True}),
            ("verification_output", {"loop": 1}),
            ("report", {"verification": 1}),
        ):
            with self.subTest(kind=kind, kwargs=kwargs), self.assertRaises(ValueError):
                self.repository.read_artifact("TASK-1", "run-0001", kind, **kwargs)

    def test_file_symlinks_cannot_escape_selected_run(self) -> None:
        secret = self.root / "secret"
        secret.write_text("private")
        (self.run / "report.json").symlink_to(secret)
        self.assertEqual(self.repository.list_runs()[0].manifest_state, "unsafe")
        (self.loop / "progress.md").symlink_to(secret)
        self.assertEqual(
            self.repository.read_artifact(
                "TASK-1", "run-0001", "progress", loop=1
            ).state,
            "unsafe",
        )
        (self.run / "report.md").write_text("internal")
        (self.loop / "iteration-1.md").symlink_to(self.run / "report.md")
        self.assertEqual(
            self.repository.read_artifact("TASK-1", "run-0001", "report", loop=1).data,
            "internal",
        )

    def test_symlinked_storage_item_run_and_loop_directories_are_rejected(self) -> None:
        other = self.root / "other"
        other.mkdir()
        (other / ".scissorhands").symlink_to(
            self.run.parent.parent, target_is_directory=True
        )
        with self.assertRaises(UnsafeArtifactPath):
            RunRepository(other).list_runs()
        (self.run.parent.parent / "ALIAS").symlink_to(
            self.run.parent, target_is_directory=True
        )
        (self.run.parent / "run-0002").symlink_to(self.run, target_is_directory=True)
        (self.run / "loop-0002").symlink_to(self.loop, target_is_directory=True)
        self.assertEqual(self.repository.list_work_items(), ("TASK-1",))
        self.assertEqual(len(self.repository.list_runs()), 1)
        self.assertEqual(self.repository.read_run("TASK-1", "run-0001").loops, (1,))
        for item, run in (("ALIAS", "run-0001"), ("TASK-1", "run-0002")):
            with self.assertRaises(UnsafeArtifactPath):
                self.repository.read_run(item, run)
        with self.assertRaises(UnsafeArtifactPath):
            self.repository.read_loop("TASK-1", "run-0001", 2)

    def test_reads_actual_service_artifacts_through_queued_and_finished_states(
        self,
    ) -> None:
        (self.root / "WORK_ITEM.toml").write_text("""id = "REAL"
title = "Actual artifacts"
description = "Exercise the writer and reader together."
definition_of_done = ["Done"]
acceptance_criteria = ["Works"]
""")

        def invoke(command, prompt, log, cwd):
            log.write_text("agent failed")
            return 1

        async def exercise():
            service = RunService(
                self.root, invoke=invoke, find_executable=lambda _: "/fake/agent"
            )
            config, paths = await service.reserve(RunRequest(agent="opencode"))
            self.assertEqual(
                self.repository.read_run("REAL", paths.run_dir.name).summary.state,
                "queued",
            )
            await service.run_reserved(config, paths)
            return paths

        with redirect_stdout(StringIO()):
            paths = asyncio.run(exercise())
        detail = self.repository.read_run("REAL", paths.run_dir.name)
        self.assertEqual(
            (detail.summary.state, detail.summary.outcome), ("finished", "agent_failed")
        )
        self.assertEqual(detail.settings.data["auto_approve"], False)
        self.assertEqual(detail.work_item.data["id"], "REAL")
        self.assertEqual(
            self.repository.read_loop("REAL", paths.run_dir.name, 1).receipt.data[
                "agent_exit_code"
            ],
            1,
        )
