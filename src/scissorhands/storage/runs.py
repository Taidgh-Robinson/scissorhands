"""Allocate run folders and preserve each loop's durable artifacts."""

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from scissorhands.core.iteration import IterationRecord
from scissorhands.core.loop.models import LoopConfig
from scissorhands.core.planning import PLAN_FILE
from scissorhands.core.status import STATUS_FILE
from scissorhands.core.verification import VerificationResult
from scissorhands.core.work_items import validate_work_item_id
from scissorhands.storage.diffs import head_commit, snapshot_worktree, write_loop_diff
from scissorhands.storage.paths import RunPaths
from scissorhands.storage.planning import copy_plan
from scissorhands.storage.receipts import write_iteration_receipt
from scissorhands.storage.reports import (
    write_loop_report,
    write_run_manifest,
    write_run_report,
)


def write_verification_logs(loop_dir: Path, verification: VerificationResult) -> None:
    for index, result in enumerate(verification.results, 1):
        (loop_dir / f"verification-{index}.log").write_text(
            result.output, encoding="utf-8"
        )


class RunWriter:
    """Persist one active run, keeping best-effort reporting out of orchestration."""

    def __init__(
        self, config: LoopConfig, paths: RunPaths, *, on_warning: Callable[[str], None]
    ) -> None:
        self.config = config
        self.paths = paths
        self._on_warning = on_warning
        self._start_tree: str | None = None

    def initialize_loop(self, number: int) -> tuple[Path, Path, Path]:
        return initialize_loop(self.paths, number)

    def capture_before(self, number: int) -> str | None:
        """Snapshot the worktree; a Git failure must not stop the agent."""
        try:
            before = snapshot_worktree(self.config.root)
        except (OSError, subprocess.CalledProcessError) as error:
            self._on_warning(
                f"Could not capture Git state before loop {number}: {getattr(error, 'stderr', error)}"
            )
            before = None
        if number == 1:
            self._start_tree = before
        return before

    def capture_changes(
        self, record: IterationRecord, before: str | None
    ) -> IterationRecord:
        after = None
        if before is not None:
            patch = self.paths.loop_dir(record.iteration) / "changes.patch"
            after = self._save_diff(before, patch, f"loop {record.iteration}")
        return replace(record, git_before_tree=before, git_after_tree=after)

    def _save_diff(self, before: str, patch: Path, description: str) -> str | None:
        after = None
        try:
            after = snapshot_worktree(self.config.root)
            if after is not None:
                write_loop_diff(self.config.root, before, after, patch)
        except (OSError, subprocess.CalledProcessError) as error:
            self._on_warning(f"Could not save Git diff for {description}: {error}")
        return after

    def save_iteration(
        self, record: IterationRecord, previous: list[IterationRecord]
    ) -> None:
        """Require a receipt, then attempt the human report and manifest update."""
        loop_dir = self.paths.loop_dir(record.iteration)
        write_iteration_receipt(loop_dir / f"iteration-{record.iteration}.json", record)
        try:
            write_loop_report(
                loop_dir,
                self.config.work_item,
                record,
                previous[-1] if previous else None,
            )
        except OSError as error:
            self._on_warning(f"Could not write loop report: {error}")
        try:
            self.update_manifest([*previous, record])
        except OSError as error:
            self._on_warning(f"Could not update run manifest: {error}")

    def update_manifest(self, records: list[IterationRecord]) -> None:
        write_run_manifest(
            self.paths.run_dir, self.config.work_item, records, self.paths.started_at
        )

    def mark_cancelled(self, records: list[IterationRecord]) -> None:
        write_run_manifest(
            self.paths.run_dir,
            self.config.work_item,
            records,
            self.paths.started_at,
            cancelled=True,
        )

    def finish(self, records: list[IterationRecord]) -> None:
        """Save the cumulative diff and terminal run reports."""
        if self._start_tree is not None:
            self._save_diff(
                self._start_tree, self.paths.run_dir / "changes.patch", "the run"
            )
        try:
            write_run_manifest(
                self.paths.run_dir,
                self.config.work_item,
                records,
                self.paths.started_at,
                finished=True,
            )
            write_run_report(self.paths.run_dir, self.config.work_item, records)
        except OSError as error:
            self._on_warning(f"Could not write run report: {error}")


def initialize_run(config: LoopConfig, *, queued: bool = False) -> RunPaths:
    """Reserve a numbered directory and persist its initial snapshots and state."""
    run_dir = _allocate_run_directory(config.root, config.work_item.id)
    started_at = datetime.now(UTC).isoformat()
    _write_initial_snapshots(config, run_dir, started_at)
    write_run_manifest(run_dir, config.work_item, [], started_at, queued=queued)
    return RunPaths(run_dir, started_at)


def _allocate_run_directory(root: Path, work_item_id: str) -> Path:
    """Allocate exclusively so concurrent reservations cannot reuse a run ID."""
    item_dir = root / ".scissorhands" / validate_work_item_id(work_item_id)
    item_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        int(match.group(1))
        for child in item_dir.iterdir()
        if child.is_dir() and (match := re.fullmatch(r"run-(\d+)", child.name))
    ]
    number = max(existing, default=0) + 1
    while True:
        run_dir = item_dir / f"run-{number:04d}"
        try:
            run_dir.mkdir(exist_ok=False)
            return run_dir
        except FileExistsError:
            number += 1


def _write_initial_snapshots(
    config: LoopConfig, run_dir: Path, started_at: str
) -> None:
    (run_dir / "work-item.json").write_text(
        json.dumps(asdict(config.work_item), indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "started_at": started_at,
                "git_head": head_commit(config.root),
                "agent": config.adapter.name,
                "executable": config.executable,
                "model": config.model,
                "max_iterations": config.max_iterations,
                "auto_approve": config.auto_approve,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if config.work_item_path is not None:
        shutil.copyfile(config.work_item_path, run_dir / "work-item.toml")


def initialize_loop(paths: RunPaths, number: int) -> tuple[Path, Path, Path]:
    loop_dir = paths.loop_dir(number)
    loop_dir.mkdir(exist_ok=False)
    progress = loop_dir / "progress.md"
    status = loop_dir / STATUS_FILE
    if number == 1:
        progress.write_text(
            "# Scissorhands progress\n\nNo iterations completed yet.\n",
            encoding="utf-8",
        )
    else:
        previous = paths.loop_dir(number - 1)
        shutil.copyfile(previous / "progress.md", progress)
        if (previous / STATUS_FILE).is_file():
            shutil.copyfile(previous / STATUS_FILE, status)
        copy_plan(previous / PLAN_FILE, loop_dir / PLAN_FILE)
    return loop_dir, status, progress
