"""Orchestrate bounded agent iterations."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from scissorhands.agents import AgentAdapter
from scissorhands.core.diffs import head_commit, snapshot_worktree, write_loop_diff
from scissorhands.core.execution import run_command
from scissorhands.core.iteration import IterationRecord
from scissorhands.core.receipts import write_iteration_receipt
from scissorhands.core.reporting import (
    report_iteration,
    report_status,
    report_verification,
)
from scissorhands.core.run_reports import (
    write_loop_report,
    write_run_manifest,
    write_run_report,
)
from scissorhands.core.status import STATUS_FILE, read_status
from scissorhands.core.verification import VerificationResult, run_verification
from scissorhands.core.work_items import WorkItem, validate_work_item_id
from scissorhands.prompting.compose import compose_prompt
from scissorhands.prompting.contract import default_contract

DEFAULT_COMPLETION_MARKER = "<promise>COMPLETE</promise>"
_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass(frozen=True, slots=True)
class LoopConfig:
    """Configuration for one bounded loop run."""

    root: Path
    work_item: WorkItem
    adapter: AgentAdapter
    executable: str
    max_iterations: int
    model: str | None = None
    auto_approve: bool = False
    completion_marker: str = DEFAULT_COMPLETION_MARKER
    contract: str = field(default_factory=default_contract)
    work_item_path: Path | None = None


@dataclass(frozen=True, slots=True)
class LoopResult:
    """Outcome and artifacts from a loop run."""

    completed: bool
    iterations: int
    run_dir: Path
    failed: bool = False


def has_completion_marker(text: str, marker: str = DEFAULT_COMPLETION_MARKER) -> bool:
    """Match a marker only when it occupies a complete output line."""
    clean = _ANSI_ESCAPE.sub("", text)
    return any(line.strip() == marker for line in clean.splitlines())


def _modified_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


Invoke = Callable[[list[str], str | None, Path, Path], int]
Verify = Callable[[Sequence[str], Path], VerificationResult]


@dataclass(frozen=True, slots=True)
class RunPaths:
    run_dir: Path
    started_at: str

    def loop_dir(self, number: int) -> Path:
        return self.run_dir / f"loop-{number:04d}"


@dataclass(frozen=True, slots=True)
class PreparedIteration:
    number: int
    prompt: str
    command: list[str]
    log: Path
    final_message: Path


def initialize_run(config: LoopConfig) -> RunPaths:
    item_dir = (
        config.root / ".scissorhands" / validate_work_item_id(config.work_item.id)
    )
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
            break
        except FileExistsError:
            number += 1
    started_at = datetime.now(UTC).isoformat()
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
    write_run_manifest(run_dir, config.work_item, [], started_at)
    return RunPaths(run_dir, started_at)


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
    return loop_dir, status, progress


def prepare_iteration(
    config: LoopConfig, loop_dir: Path, number: int, feedback: str | None
) -> PreparedIteration:
    progress_path = str((loop_dir / "progress.md").relative_to(config.root))
    status_path = str((loop_dir / STATUS_FILE).relative_to(config.root))
    prompt = compose_prompt(
        config.work_item,
        number,
        config.completion_marker,
        max_iterations=config.max_iterations,
        verification_feedback=feedback,
        contract=config.contract,
        progress_path=progress_path,
        status_path=status_path,
    )
    (loop_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    final_message = loop_dir / f"iteration-{number}.final.txt"
    command = config.adapter.command(
        executable=config.executable,
        root=config.root,
        final_message=final_message,
        model=config.model,
        auto_approve=config.auto_approve,
        prompt=prompt,
    )
    return PreparedIteration(
        number, prompt, command, loop_dir / f"iteration-{number}.log", final_message
    )


def execute_iteration(
    config: LoopConfig,
    prepared: PreparedIteration,
    status: Path,
    progress: Path,
    *,
    invoke: Invoke,
    verify: Verify,
) -> IterationRecord:
    print(
        f"\n=== Scissorhands iteration {prepared.number}/{config.max_iterations} "
        f"({config.adapter.name}) ==="
    )
    status_before = _modified_ns(status)
    progress_before = _modified_ns(progress)
    stdin_prompt = prepared.prompt if config.adapter.uses_stdin else None
    started_at = datetime.now(UTC).isoformat()
    started = perf_counter()
    return_code = invoke(prepared.command, stdin_prompt, prepared.log, config.root)
    agent_elapsed_seconds = perf_counter() - started
    status_updated = _modified_ns(status) != status_before
    progress_updated = _modified_ns(progress) != progress_before
    statuses = read_status(status, config.work_item.checklist())
    claimed = False
    verification = None
    verification_elapsed_seconds = None
    if return_code == 0:
        report_status(status, statuses, updated=status_updated)
        output = config.adapter.completion_output(
            log=prepared.log, final_message=prepared.final_message
        )
        claimed = has_completion_marker(output, config.completion_marker)
        if config.work_item.verification:
            verification_started = perf_counter()
            verification = verify(config.work_item.verification, config.root)
            verification_elapsed_seconds = perf_counter() - verification_started
            for index, result in enumerate(verification.results, 1):
                (prepared.log.parent / f"verification-{index}.log").write_text(
                    result.output, encoding="utf-8"
                )
            report_verification(verification)
    elapsed_seconds = perf_counter() - started
    finished_at = datetime.now(UTC).isoformat()
    return IterationRecord(
        iteration=prepared.number,
        agent=config.adapter.name,
        agent_exit_code=return_code,
        statuses=statuses,
        status_updated=status_updated,
        progress=_read_text(progress),
        progress_updated=progress_updated,
        verification=verification,
        verification_required=bool(config.work_item.verification),
        marker_claimed=claimed,
        final_iteration=prepared.number == config.max_iterations,
        elapsed_seconds=elapsed_seconds,
        started_at=started_at,
        finished_at=finished_at,
        agent_elapsed_seconds=agent_elapsed_seconds,
        verification_elapsed_seconds=verification_elapsed_seconds,
    )


def write_final_artifacts(
    config: LoopConfig,
    paths: RunPaths,
    records: list[IterationRecord],
    start: str | None,
) -> None:
    """Save the cumulative patch and run report after the final loop."""
    if start is not None:
        try:
            end = snapshot_worktree(config.root)
            if end is not None:
                write_loop_diff(
                    config.root, start, end, paths.run_dir / "changes.patch"
                )
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"Could not save final Git diff: {error}", file=sys.stderr)
    try:
        write_run_manifest(
            paths.run_dir, config.work_item, records, paths.started_at, finished=True
        )
        write_run_report(paths.run_dir, config.work_item, records)
    except OSError as error:
        print(f"Could not write run report: {error}", file=sys.stderr)


def run_loop(
    config: LoopConfig,
    *,
    invoke: Invoke = run_command,
    verify: Verify = run_verification,
) -> LoopResult:
    """Run fresh agent sessions until completion, failure, or the configured bound."""
    if config.max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    paths = initialize_run(config)
    feedback: str | None = None
    records: list[IterationRecord] = []
    start_tree: str | None = None
    for number in range(1, config.max_iterations + 1):
        loop_dir, status, progress = initialize_loop(paths, number)
        prepared = prepare_iteration(config, loop_dir, number, feedback)
        try:
            before = snapshot_worktree(config.root)
        except (OSError, subprocess.CalledProcessError) as error:
            before = None
            print(
                f"Could not capture Git state before loop {number}: {getattr(error, 'stderr', error)}",
                file=sys.stderr,
            )
        if number == 1:
            start_tree = before
        record = execute_iteration(
            config, prepared, status, progress, invoke=invoke, verify=verify
        )
        after = None
        if before is not None:
            try:
                after = snapshot_worktree(config.root)
                if after is not None:
                    write_loop_diff(
                        config.root, before, after, loop_dir / "changes.patch"
                    )
            except (OSError, subprocess.CalledProcessError) as error:
                print(
                    f"Could not save Git diff for loop {number}: {error}",
                    file=sys.stderr,
                )
        record = replace(record, git_before_tree=before, git_after_tree=after)
        write_iteration_receipt(loop_dir / f"iteration-{number}.json", record)
        try:
            write_loop_report(
                loop_dir, config.work_item, record, records[-1] if records else None
            )
        except OSError as error:
            print(f"Could not write loop report: {error}", file=sys.stderr)
        records.append(record)
        try:
            write_run_manifest(
                paths.run_dir, config.work_item, records, paths.started_at
            )
        except OSError as error:
            print(f"Could not update run manifest: {error}", file=sys.stderr)
        report_iteration(record, prepared.log)
        decision = record.decision
        if decision.accepted or decision.outcome == "agent_failed":
            write_final_artifacts(config, paths, records, start_tree)
            return LoopResult(
                completed=decision.accepted,
                iterations=number,
                run_dir=paths.run_dir,
                failed=decision.outcome == "agent_failed",
            )
        feedback = record.verification_feedback
    write_final_artifacts(config, paths, records, start_tree)
    return LoopResult(
        completed=False,
        iterations=config.max_iterations,
        run_dir=paths.run_dir,
    )
