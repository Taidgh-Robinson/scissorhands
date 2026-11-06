import asyncio
import json
import subprocess
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scissorhands.agents import OpenCodeAdapter
from scissorhands.cli.reporting import TerminalReporter
from scissorhands.core.loop.iteration import has_completion_marker
from scissorhands.core.loop.models import LoopConfig
from scissorhands.core.loop.runner import (
    run_loop as async_run_loop,
)
from scissorhands.core.verification import CommandResult, VerificationResult
from scissorhands.core.work_items import WorkItem
from scissorhands.prompting.compose import compose_prompt
from scissorhands.storage.runs import initialize_run

WORK_ITEM = WorkItem(
    id="WORK-ITEM",
    title="Build the thing",
    description="Build the requested thing.",
    definition_of_done=("Tests pass.",),
    acceptance_criteria=("The thing works.",),
)
VERIFIED_WORK_ITEM = replace(WORK_ITEM, verification=("make test",))
MARKER = "<promise>COMPLETE</promise>"


def run_loop(*args, **kwargs):
    kwargs.setdefault("observer", TerminalReporter())
    return asyncio.run(async_run_loop(*args, **kwargs))


def active_status(root: Path) -> Path:
    loop_dir = sorted((root / ".scissorhands" / WORK_ITEM.id).glob("run-*/loop-*"))[-1]
    return loop_dir / "status.json"


def write_fully_met_status(root: Path, evidence: str = "Checked.") -> None:
    active_status(root).write_text(
        json.dumps(
            {
                "DoD-1": {"met": True, "evidence": evidence},
                "AC-1": {"met": True, "evidence": evidence},
            }
        ),
        encoding="utf-8",
    )


class CompletionMarkerTests(TestCase):
    def test_marker_must_occupy_a_line(self) -> None:
        self.assertTrue(has_completion_marker("Done\n<promise>COMPLETE</promise>\n"))
        self.assertFalse(
            has_completion_marker("Use <promise>COMPLETE</promise> when done")
        )

    def test_ansi_formatting_is_ignored(self) -> None:
        self.assertTrue(
            has_completion_marker("\x1b[32m<promise>COMPLETE</promise>\x1b[0m")
        )


class LoopTests(TestCase):
    def test_each_loop_saves_only_its_git_changes_without_staging_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args: str) -> str:
                return subprocess.run(
                    ["git", "-C", str(root), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout

            git("init", "-q")
            (root / ".gitignore").write_text(".scissorhands/\n", encoding="utf-8")
            (root / "code.py").write_text("base\n", encoding="utf-8")
            (root / "staged.py").write_text("original\n", encoding="utf-8")
            git("add", ".gitignore", "code.py", "staged.py")
            git(
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-qm",
                "base",
            )
            (root / "code.py").write_text("existing edit\n", encoding="utf-8")
            (root / "staged.py").write_text("already staged\n", encoding="utf-8")
            git("add", "staged.py")
            initial_index = git("diff", "--cached")
            calls = 0

            def invoke(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                nonlocal calls
                calls += 1
                if calls == 1:
                    (root / "code.py").write_text("first loop\n", encoding="utf-8")
                    (root / "new.py").write_text("new file\n", encoding="utf-8")
                else:
                    (root / "code.py").write_text("second loop\n", encoding="utf-8")
                    (root / "new.py").write_text("changed new file\n", encoding="utf-8")
                log.write_text("working\n", encoding="utf-8")
                return 0

            result = run_loop(
                LoopConfig(root, WORK_ITEM, OpenCodeAdapter(), "opencode", 2),
                invoke=invoke,
            )
            first = (result.run_dir / "loop-0001" / "changes.patch").read_text()
            second = (result.run_dir / "loop-0002" / "changes.patch").read_text()
            full = (result.run_dir / "changes.patch").read_text()
            self.assertIn("-existing edit", first)
            self.assertIn("+first loop", first)
            self.assertIn("+new file", first)
            self.assertNotIn("already staged", first)
            self.assertIn("-first loop", second)
            self.assertIn("+second loop", second)
            self.assertIn("-new file", second)
            self.assertIn("+changed new file", second)
            self.assertNotIn("existing edit", second)
            self.assertNotIn(".scissorhands", first + second)
            self.assertIn("-existing edit", full)
            self.assertIn("+second loop", full)
            self.assertIn("+changed new file", full)
            self.assertNotIn("+first loop", full)
            self.assertNotIn(".scissorhands", full)
            self.assertEqual(git("diff", "--cached"), initial_index)
            self.assertEqual(
                json.loads((result.run_dir / "run.json").read_text())["git_head"],
                git("rev-parse", "HEAD").strip(),
            )
            first_receipt = json.loads(
                (result.run_dir / "loop-0001" / "iteration-1.json").read_text()
            )
            second_receipt = json.loads(
                (result.run_dir / "loop-0002" / "iteration-2.json").read_text()
            )
            self.assertEqual(
                git(
                    "diff",
                    "--binary",
                    "--no-ext-diff",
                    "--no-color",
                    first_receipt["git_before_tree"],
                    first_receipt["git_after_tree"],
                ),
                first,
            )
            self.assertEqual(
                first_receipt["git_after_tree"], second_receipt["git_before_tree"]
            )
            self.assertIn(
                "[Code changes](changes.patch)",
                (result.run_dir / "loop-0001" / "iteration-1.md").read_text(),
            )
            self.assertIn(
                "[Full code changes](changes.patch)",
                (result.run_dir / "report.md").read_text(),
            )

    def test_run_numbers_are_exclusive_and_interrupted_runs_are_retained(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = LoopConfig(root, WORK_ITEM, OpenCodeAdapter(), "opencode", 1)
            with ThreadPoolExecutor(max_workers=4) as pool:
                run_dirs = list(
                    pool.map(lambda _: initialize_run(config).run_dir, range(4))
                )
            self.assertEqual(
                {path.name for path in run_dirs},
                {"run-0001", "run-0002", "run-0003", "run-0004"},
            )
            self.assertEqual(initialize_run(config).run_dir.name, "run-0005")

    def test_manifest_retains_completed_loops_after_interruption(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0

            def invoke(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                nonlocal calls
                calls += 1
                manifest = json.loads((log.parent.parent / "report.json").read_text())
                self.assertEqual(manifest["state"], "running")
                self.assertIsNone(manifest["outcome"])
                self.assertEqual(len(manifest["loops"]), calls - 1)
                if calls == 2:
                    raise KeyboardInterrupt
                log.write_text("working\n", encoding="utf-8")
                return 0

            config = LoopConfig(root, WORK_ITEM, OpenCodeAdapter(), "opencode", 3)
            with self.assertRaises(KeyboardInterrupt):
                run_loop(config, invoke=invoke)
            run_dir = root / ".scissorhands" / WORK_ITEM.id / "run-0001"
            manifest = json.loads((run_dir / "report.json").read_text())
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["run_id"], "run-0001")
            self.assertEqual(manifest["state"], "running")
            self.assertIsNone(manifest["finished_at"])
            self.assertEqual(len(manifest["loops"]), 1)
            self.assertEqual(manifest["loops"][0]["loop"], 1)
            self.assertTrue((run_dir / manifest["loops"][0]["receipt"]).is_file())

    def test_loop_state_and_reports_are_saved_under_numbered_folders(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "WORK_ITEM.toml"
            source.write_text('id = "WORK-ITEM"\n', encoding="utf-8")
            prompts = []

            def invoke(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                prompts.append(command[-1])
                self.assertEqual(log.parent.name, f"loop-{len(prompts):04d}")
                self.assertIn(
                    str(log.parent.relative_to(root) / "status.json"), command[-1]
                )
                if len(prompts) == 2:
                    self.assertEqual(
                        (log.parent / "progress.md").read_text(), "Step 1.\n"
                    )
                    self.assertTrue(active_status(root).exists())
                active_status(root).write_text(
                    json.dumps({"DoD-1": {"met": False}, "AC-1": {"met": False}}),
                    encoding="utf-8",
                )
                (log.parent / "progress.md").write_text(
                    f"Step {len(prompts)}.\n", encoding="utf-8"
                )
                log.write_text("working\n", encoding="utf-8")
                return 0

            config = LoopConfig(
                root, WORK_ITEM, OpenCodeAdapter(), "opencode", 2, work_item_path=source
            )
            first = run_loop(config, invoke=invoke)
            self.assertEqual(
                first.run_dir, root / ".scissorhands" / "WORK-ITEM" / "run-0001"
            )
            self.assertEqual(
                (first.run_dir / "work-item.toml").read_text(), source.read_text()
            )
            self.assertEqual(
                json.loads((first.run_dir / "work-item.json").read_text())["id"],
                "WORK-ITEM",
            )
            self.assertEqual(
                json.loads((first.run_dir / "run.json").read_text())["max_iterations"],
                2,
            )
            second_loop = first.run_dir / "loop-0002"
            self.assertEqual((second_loop / "progress.md").read_text(), "Step 2.\n")
            self.assertTrue((second_loop / "prompt.md").exists())
            self.assertTrue((second_loop / "iteration-2.json").exists())
            self.assertGreater(
                json.loads((second_loop / "iteration-2.json").read_text())[
                    "elapsed_seconds"
                ],
                0,
            )
            receipt = json.loads((second_loop / "iteration-2.json").read_text())
            self.assertLessEqual(
                datetime.fromisoformat(receipt["started_at"]),
                datetime.fromisoformat(receipt["finished_at"]),
            )
            self.assertGreater(receipt["agent_elapsed_seconds"], 0)
            self.assertIsNone(receipt["verification_elapsed_seconds"])
            self.assertGreaterEqual(
                receipt["elapsed_seconds"], receipt["agent_elapsed_seconds"]
            )
            self.assertTrue((second_loop / "iteration-2.md").exists())
            self.assertIn("iteration_limit", (first.run_dir / "report.md").read_text())
            manifest = json.loads((first.run_dir / "report.json").read_text())
            self.assertEqual(manifest["outcome"], "iteration_limit")
            self.assertEqual(manifest["state"], "finished")
            self.assertIsNotNone(manifest["finished_at"])
            self.assertEqual(
                manifest["started_at"],
                json.loads((first.run_dir / "run.json").read_text())["started_at"],
            )
            self.assertEqual(len(manifest["loops"]), 2)

            def fresh_run(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                self.assertFalse(active_status(root).exists())
                self.assertIn(
                    "No iterations completed yet",
                    (log.parent / "progress.md").read_text(),
                )
                log.write_text("failed\n", encoding="utf-8")
                return 1

            self.assertEqual(
                run_loop(config, invoke=fresh_run).run_dir.name, "run-0002"
            )

    def test_loop_repeats_until_completion(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0

            def fake_invoke(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                nonlocal calls
                calls += 1
                self.assertEqual(cwd, root)
                self.assertIsNone(prompt)
                self.assertIn(f"iteration {calls}", command[-1])
                output = (
                    "still working\n" if calls == 1 else "<promise>COMPLETE</promise>\n"
                )
                write_fully_met_status(root, evidence=f"Checked in iteration {calls}.")
                log.write_text(output, encoding="utf-8")
                return 0

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=fake_invoke,
            )

            self.assertTrue(result.completed)
            self.assertEqual(result.iterations, 2)
            self.assertEqual(calls, 2)
            self.assertTrue((result.run_dir / "loop-0001" / "progress.md").exists())
            first_receipt = json.loads(
                (result.run_dir / "loop-0001" / "iteration-1.json").read_text(
                    encoding="utf-8"
                )
            )
            second_receipt = json.loads(
                (result.run_dir / "loop-0002" / "iteration-2.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(first_receipt["outcome"], "continuing")
            self.assertFalse(first_receipt["completion_marker_claimed"])
            self.assertFalse(first_receipt["progress_updated"])
            self.assertIn("# Scissorhands progress", first_receipt["progress"])
            self.assertTrue(first_receipt["status_readable"])
            self.assertEqual(first_receipt["criteria"][0]["id"], "DoD-1")
            self.assertEqual(second_receipt["outcome"], "completed")
            self.assertTrue(second_receipt["completion_accepted"])

    def test_loop_stops_on_agent_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def fail(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                log.write_text("failed", encoding="utf-8")
                return 7

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=fail,
            )

            self.assertTrue(result.failed)
            self.assertEqual(result.iterations, 1)
            self.assertEqual(
                json.loads((result.run_dir / "report.json").read_text())["outcome"],
                "agent_failed",
            )
            receipt = json.loads(
                (result.run_dir / "loop-0001" / "iteration-1.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(receipt["agent_exit_code"], 7)
            self.assertEqual(receipt["outcome"], "agent_failed")

    def test_verification_is_skipped_without_commands(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def complete(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                write_fully_met_status(root)
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            def unexpected_verify(
                commands: Sequence[str], cwd: Path
            ) -> VerificationResult:
                self.fail("verification should not run without commands")

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=complete,
                verify=unexpected_verify,
            )

            self.assertTrue(result.completed)
            self.assertEqual(result.iterations, 1)

    def test_marker_is_ignored_until_verification_passes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompts: list[str] = []
            verify_calls = 0

            def complete(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                prompts.append(command[-1])
                write_fully_met_status(
                    root, evidence=f"Checked before verification {len(prompts)}."
                )
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            def verify(commands: Sequence[str], cwd: Path) -> VerificationResult:
                nonlocal verify_calls
                verify_calls += 1
                self.assertEqual(list(commands), ["make test"])
                self.assertEqual(cwd, root)
                code = 1 if verify_calls == 1 else 0
                return VerificationResult(
                    (CommandResult("make test", code, "FAILED test_thing\n"),)
                )

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=VERIFIED_WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=3,
                ),
                invoke=complete,
                verify=verify,
            )

            self.assertTrue(result.completed)
            self.assertEqual(result.iterations, 2)
            self.assertNotIn("## Verification feedback", prompts[0])
            self.assertIn("## Verification feedback", prompts[1])
            self.assertIn("FAILED test_thing", prompts[1])
            first_receipt = json.loads(
                (result.run_dir / "loop-0001" / "iteration-1.json").read_text(
                    encoding="utf-8"
                )
            )
            second_receipt = json.loads(
                (result.run_dir / "loop-0002" / "iteration-2.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(first_receipt["verification"]["passed"])
            self.assertGreaterEqual(first_receipt["verification_elapsed_seconds"], 0)
            self.assertGreaterEqual(
                first_receipt["elapsed_seconds"],
                first_receipt["agent_elapsed_seconds"]
                + first_receipt["verification_elapsed_seconds"],
            )
            self.assertEqual(
                first_receipt["verification"]["commands"][0]["return_code"], 1
            )
            self.assertTrue(second_receipt["verification"]["passed"])
            self.assertEqual(
                (result.run_dir / "loop-0001" / "verification-1.log").read_text(),
                "FAILED test_thing\n",
            )
            self.assertIn("failed (exit 1)", (result.run_dir / "report.md").read_text())
            self.assertIn("passed", (result.run_dir / "report.md").read_text())

    def test_marker_is_ignored_without_a_fresh_status(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".scissorhands").mkdir()
            (root / ".scissorhands" / "status.json").write_text(
                '{"DoD-1": {"met": true, "evidence": "old"}}', encoding="utf-8"
            )

            def claim_without_update(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=1,
                ),
                invoke=claim_without_update,
            )

            self.assertFalse(result.completed)

    def test_marker_is_ignored_until_every_criterion_is_met(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def claim_with_unmet_criterion(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                active_status(root).write_text(
                    json.dumps(
                        {
                            "DoD-1": {"met": True},
                            "AC-1": {"met": False},
                        }
                    ),
                    encoding="utf-8",
                )
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=1,
                ),
                invoke=claim_with_unmet_criterion,
            )

            self.assertFalse(result.completed)

    def test_marker_is_ignored_when_evidence_is_missing_or_blank(self) -> None:
        for label, dod_entry in (
            ("missing", {"met": True}),
            ("blank", {"met": True, "evidence": "  \n"}),
        ):
            with self.subTest(label=label), TemporaryDirectory() as directory:
                root = Path(directory)

                def claim_without_evidence(
                    command: list[str],
                    prompt: str | None,
                    log: Path,
                    cwd: Path,
                    status_root: Path = root,
                    status_entry: dict[str, object] = dod_entry,
                ) -> int:
                    active_status(status_root).write_text(
                        json.dumps(
                            {
                                "DoD-1": status_entry,
                                "AC-1": {"met": True, "evidence": "Observed it."},
                            }
                        ),
                        encoding="utf-8",
                    )
                    log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                    return 0

                errors = StringIO()
                with redirect_stderr(errors):
                    result = run_loop(
                        LoopConfig(
                            root=root,
                            work_item=WORK_ITEM,
                            adapter=OpenCodeAdapter(),
                            executable="opencode",
                            max_iterations=1,
                        ),
                        invoke=claim_without_evidence,
                    )

                self.assertFalse(result.completed)
                self.assertIn("missing evidence: DoD-1", errors.getvalue())

    def test_failing_verification_exhausts_the_iteration_limit(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def complete(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                log.write_text("<promise>COMPLETE</promise>\n", encoding="utf-8")
                return 0

            def always_fail(commands: Sequence[str], cwd: Path) -> VerificationResult:
                return VerificationResult((CommandResult("make test", 1, ""),))

            result = run_loop(
                LoopConfig(
                    root=root,
                    work_item=VERIFIED_WORK_ITEM,
                    adapter=OpenCodeAdapter(),
                    executable="opencode",
                    max_iterations=2,
                ),
                invoke=complete,
                verify=always_fail,
            )

            self.assertFalse(result.completed)
            self.assertFalse(result.failed)
            self.assertEqual(result.iterations, 2)

    def test_reports_agent_criteria_status(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def write_status(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                active_status(root).write_text(
                    json.dumps(
                        {
                            "DoD-1": {"met": True, "evidence": "Ran the tests."},
                            "AC-1": {"met": False},
                        }
                    ),
                    encoding="utf-8",
                )
                log.write_text("still working\n", encoding="utf-8")
                return 0

            output = StringIO()
            with redirect_stdout(output):
                run_loop(
                    LoopConfig(
                        root=root,
                        work_item=WORK_ITEM,
                        adapter=OpenCodeAdapter(),
                        executable="opencode",
                        max_iterations=1,
                    ),
                    invoke=write_status,
                )

            self.assertIn("[x] DoD-1: Tests pass.", output.getvalue())
            self.assertIn("Ran the tests.", output.getvalue())
            self.assertIn("[ ] AC-1: The thing works.", output.getvalue())
            self.assertNotIn("not updated this iteration", output.getvalue())

    def test_flags_status_that_was_not_updated(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0

            def idle(
                command: list[str], prompt: str | None, log: Path, cwd: Path
            ) -> int:
                nonlocal calls
                calls += 1
                if calls == 1:
                    active_status(root).write_text(
                        '{"AC-1": {"met": true}}', encoding="utf-8"
                    )
                log.write_text("still working\n", encoding="utf-8")
                return 0

            output = StringIO()
            with redirect_stdout(output):
                run_loop(
                    LoopConfig(
                        root=root,
                        work_item=WORK_ITEM,
                        adapter=OpenCodeAdapter(),
                        executable="opencode",
                        max_iterations=2,
                    ),
                    invoke=idle,
                )

            self.assertIn("(not updated this iteration)", output.getvalue())
            self.assertIn("[?] DoD-1: Tests pass.", output.getvalue())


class ComposePromptTests(TestCase):
    def test_completion_requires_definition_of_done_and_acceptance(self) -> None:
        prompt = compose_prompt(WORK_ITEM, 1, MARKER, max_iterations=3)

        self.assertIn(
            "every definition of done item and every acceptance criterion", prompt
        )

    def test_prompt_states_the_iteration_budget(self) -> None:
        prompt = compose_prompt(WORK_ITEM, 2, MARKER, max_iterations=5)

        self.assertIn("This is iteration 2 of 5.", prompt)
        self.assertNotIn("This is the final iteration.", prompt)

    def test_final_iteration_asks_for_a_clean_handoff(self) -> None:
        prompt = compose_prompt(WORK_ITEM, 5, MARKER, max_iterations=5)

        self.assertIn("This is iteration 5 of 5.", prompt)
        self.assertIn("This is the final iteration.", prompt)
        self.assertIn("Do not start large new pieces of work.", prompt)

    def test_prompt_asks_for_status_keyed_by_id(self) -> None:
        prompt = compose_prompt(WORK_ITEM, 1, MARKER, max_iterations=3)

        self.assertIn("`.scissorhands/status.json`", prompt)
        self.assertIn('"DoD-1": {"met": true', prompt)
