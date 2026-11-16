"""Orchestrate bounded iterations; storage and presentation are separate concerns."""

from __future__ import annotations

import asyncio
from functools import partial

from scissorhands.core.iteration import IterationRecord
from scissorhands.core.loop.iteration import execute_iteration, prepare_iteration
from scissorhands.core.loop.models import Invoke, LoopConfig, LoopResult, Verify
from scissorhands.core.loop.observer import RunObserver
from scissorhands.core.loop.processes import run_command
from scissorhands.core.loop.verification import run_verification
from scissorhands.core.planning import ImplementationPlan
from scissorhands.storage.paths import RunPaths
from scissorhands.storage.runs import RunWriter, initialize_run


async def run_loop(
    config: LoopConfig,
    *,
    invoke: Invoke | None = None,
    verify: Verify = run_verification,
    paths: RunPaths | None = None,
    observer: RunObserver | None = None,
) -> LoopResult:
    """Run fresh sessions until completion, agent failure, or the iteration limit."""
    if config.max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    observer = observer if observer is not None else RunObserver()
    if invoke is None:
        invoke = partial(run_command, on_output=observer.on_output)
    reserved = paths is not None
    if paths is None:
        paths = await asyncio.to_thread(initialize_run, config)
    writer = RunWriter(config, paths, on_warning=observer.on_warning)
    records: list[IterationRecord] = []
    feedback: str | None = None
    planning_feedback: str | None = None
    previous_plan: ImplementationPlan | None = None
    try:
        if reserved:
            await asyncio.to_thread(writer.update_manifest, records)
        for number in range(1, config.max_iterations + 1):
            record = await _run_iteration(
                config,
                writer,
                number,
                feedback,
                invoke,
                verify,
                observer,
                planning_feedback,
                previous_plan,
            )
            await asyncio.to_thread(writer.save_iteration, record, records)
            records.append(record)
            observer.on_iteration_finished(
                record, paths.loop_dir(number) / f"iteration-{number}.log"
            )
            if record.decision.accepted or record.decision.outcome == "agent_failed":
                break
            feedback = record.verification_feedback
            planning_feedback = record.planning_feedback
            if record.plan is not None and record.planning_problem is None:
                previous_plan = record.plan
        await asyncio.to_thread(writer.finish, records)
    except asyncio.CancelledError:
        await asyncio.to_thread(writer.mark_cancelled, records)
        raise
    final = records[-1]
    return LoopResult(
        completed=final.decision.accepted,
        iterations=len(records),
        run_dir=paths.run_dir,
        failed=final.decision.outcome == "agent_failed",
    )


async def _run_iteration(
    config: LoopConfig,
    writer: RunWriter,
    number: int,
    feedback: str | None,
    invoke: Invoke,
    verify: Verify,
    observer: RunObserver,
    planning_feedback: str | None,
    previous_plan: ImplementationPlan | None,
) -> IterationRecord:
    loop_dir, status, progress = await asyncio.to_thread(writer.initialize_loop, number)
    prepared = await asyncio.to_thread(
        prepare_iteration, config, loop_dir, number, feedback, planning_feedback
    )
    before = await asyncio.to_thread(writer.capture_before, number)
    record = await execute_iteration(
        config,
        prepared,
        status,
        progress,
        invoke=invoke,
        verify=verify,
        observer=observer,
        previous_plan=previous_plan,
    )
    return await asyncio.to_thread(writer.capture_changes, record, before)
