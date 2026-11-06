"""Prepare and execute one iteration, collecting claims and verification."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from scissorhands.core.iteration import IterationRecord
from scissorhands.core.loop.models import (
    DEFAULT_COMPLETION_MARKER,
    Invoke,
    LoopConfig,
    PreparedIteration,
    Verify,
)
from scissorhands.core.loop.observer import RunObserver
from scissorhands.core.status import STATUS_FILE
from scissorhands.core.verification import VerificationResult
from scissorhands.prompting.compose import compose_prompt
from scissorhands.storage.agent_state import (
    read_agent_state,
    read_modification_times,
    read_progress,
)
from scissorhands.storage.runs import write_verification_logs

_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def has_completion_marker(text: str, marker: str = DEFAULT_COMPLETION_MARKER) -> bool:
    """Match a marker only when it occupies a complete output line."""
    clean = _ANSI_ESCAPE.sub("", text)
    return any(line.strip() == marker for line in clean.splitlines())


async def call_backend(callback: Callable, *args):
    """Await native async callbacks or move synchronous integrations to a thread."""
    if inspect.iscoroutinefunction(callback):
        return await callback(*args)
    result = await asyncio.to_thread(callback, *args)
    return await result if inspect.isawaitable(result) else result


def build_iteration(
    config: LoopConfig, loop_dir: Path, number: int, feedback: str | None
) -> PreparedIteration:
    """Build a prompt and command without writing files, also used for previews."""
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


def prepare_iteration(
    config: LoopConfig, loop_dir: Path, number: int, feedback: str | None
) -> PreparedIteration:
    """Build the agent invocation and persist its prompt for this loop."""
    prepared = build_iteration(config, loop_dir, number, feedback)
    (loop_dir / "prompt.md").write_text(prepared.prompt, encoding="utf-8")
    return prepared


async def execute_iteration(
    config: LoopConfig,
    prepared: PreparedIteration,
    status: Path,
    progress: Path,
    *,
    invoke: Invoke,
    verify: Verify,
    observer: RunObserver,
) -> IterationRecord:
    """Invoke the agent, inspect its claims, and run independent verification."""
    observer.on_iteration_started(
        prepared.number, config.max_iterations, config.adapter.name
    )
    status_before, progress_before = await asyncio.to_thread(
        read_modification_times, status, progress
    )
    started_at = datetime.now(UTC).isoformat()
    started = perf_counter()
    stdin_prompt = prepared.prompt if config.adapter.uses_stdin else None
    return_code = await call_backend(
        invoke, prepared.command, stdin_prompt, prepared.log, config.root
    )
    agent_elapsed_seconds = perf_counter() - started
    state = await asyncio.to_thread(
        read_agent_state, status, progress, config.work_item.checklist()
    )
    status_updated = state.status_modified_ns != status_before
    progress_updated = state.progress_modified_ns != progress_before

    claimed = False
    verification = None
    verification_elapsed_seconds = None
    if return_code == 0:
        observer.on_status(status, state.statuses, updated=status_updated)
        claimed = await _read_completion_claim(config, prepared)
        if config.work_item.verification:
            verification, verification_elapsed_seconds = await _verify_iteration(
                config, prepared, verify
            )
            observer.on_verification(verification)

    return IterationRecord(
        iteration=prepared.number,
        agent=config.adapter.name,
        agent_exit_code=return_code,
        statuses=state.statuses,
        status_updated=status_updated,
        progress=await asyncio.to_thread(read_progress, progress),
        progress_updated=progress_updated,
        verification=verification,
        verification_required=bool(config.work_item.verification),
        marker_claimed=claimed,
        final_iteration=prepared.number == config.max_iterations,
        elapsed_seconds=perf_counter() - started,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        agent_elapsed_seconds=agent_elapsed_seconds,
        verification_elapsed_seconds=verification_elapsed_seconds,
    )


async def _read_completion_claim(
    config: LoopConfig, prepared: PreparedIteration
) -> bool:
    output = await asyncio.to_thread(
        config.adapter.completion_output,
        log=prepared.log,
        final_message=prepared.final_message,
    )
    return has_completion_marker(output, config.completion_marker)


async def _verify_iteration(
    config: LoopConfig,
    prepared: PreparedIteration,
    verify: Verify,
) -> tuple[VerificationResult, float]:
    started = perf_counter()
    result = await call_backend(verify, config.work_item.verification, config.root)
    elapsed = perf_counter() - started
    await asyncio.to_thread(write_verification_logs, prepared.log.parent, result)
    return result, elapsed
