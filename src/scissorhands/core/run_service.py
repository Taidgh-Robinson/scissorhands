"""Application-facing preparation and execution of agent runs."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scissorhands.agents import ADAPTERS, get_adapter
from scissorhands.core.execution import run_command
from scissorhands.core.runner import (
    DEFAULT_COMPLETION_MARKER,
    Invoke,
    LoopConfig,
    LoopResult,
    RunPaths,
    Verify,
    initialize_run,
    run_loop,
)
from scissorhands.core.verification import run_verification
from scissorhands.core.work_items import load_work_item
from scissorhands.prompting.compose import compose_prompt
from scissorhands.prompting.contract import default_contract, load_contract


@dataclass(frozen=True, slots=True)
class RunRequest:
    """Inputs shared by the CLI and future application interfaces."""

    work_item_path: Path = Path("WORK_ITEM.toml")
    agent: str = "codex"
    max_iterations: int = 5
    model: str | None = None
    executable: str | None = None
    auto_approve: bool = False
    contract_path: Path | None = None


@dataclass(frozen=True, slots=True)
class RunPreview:
    """The first command and prompt, without creating run artifacts."""

    command: tuple[str, ...]
    prompt: str
    uses_stdin: bool


class RunService:
    """Validate and prepare runs before handing execution to the loop core."""

    def __init__(
        self,
        root: Path,
        *,
        invoke: Invoke = run_command,
        verify: Verify = run_verification,
        find_executable: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.root = root.expanduser().resolve()
        self._invoke = invoke
        self._verify = verify
        self._find_executable = find_executable

    def prepare(self, request: RunRequest) -> LoopConfig:
        """Resolve a request to validated, backend-neutral loop configuration."""
        if not self.root.is_dir():
            raise ValueError(
                f"Project root does not exist or is not a directory: {self.root}"
            )
        if request.max_iterations < 1:
            raise ValueError("--max-iterations must be at least 1")
        work_item_path = (
            request.work_item_path
            if request.work_item_path.is_absolute()
            else self.root / request.work_item_path
        )
        if not work_item_path.is_file():
            raise ValueError(f"Work item does not exist: {work_item_path}")
        if request.agent not in ADAPTERS:
            raise ValueError(f"Unknown agent: {request.agent}")
        executable = request.executable or request.agent
        resolved = self._find_executable(executable)
        if resolved is None:
            raise ValueError(f"Agent executable not found: {executable}")
        work_item = load_work_item(work_item_path)
        contract_path = request.contract_path
        if contract_path is not None and not contract_path.is_absolute():
            contract_path = self.root / contract_path
        contract = (
            load_contract(contract_path)
            if contract_path is not None
            else default_contract()
        )
        return LoopConfig(
            root=self.root,
            work_item=work_item,
            contract=contract,
            adapter=get_adapter(request.agent),
            executable=resolved,
            max_iterations=request.max_iterations,
            model=request.model,
            auto_approve=request.auto_approve,
            work_item_path=work_item_path,
        )

    def preview(self, request: RunRequest) -> RunPreview:
        """Render the first iteration without writing files or invoking an agent."""
        config = self.prepare(request)
        prompt = compose_prompt(
            config.work_item,
            1,
            DEFAULT_COMPLETION_MARKER,
            max_iterations=config.max_iterations,
            contract=config.contract,
            progress_path=f".scissorhands/{config.work_item.id}/run-DRY-RUN/loop-0001/progress.md",
            status_path=f".scissorhands/{config.work_item.id}/run-DRY-RUN/loop-0001/status.json",
        )
        final_message = (
            config.root
            / ".scissorhands"
            / config.work_item.id
            / "run-DRY-RUN"
            / "loop-0001"
            / "iteration-1.final.txt"
        )
        command = config.adapter.command(
            executable=config.executable,
            root=config.root,
            final_message=final_message,
            model=config.model,
            auto_approve=config.auto_approve,
            prompt=prompt,
        )
        return RunPreview(tuple(command), prompt, config.adapter.uses_stdin)

    async def run(self, request: RunRequest) -> LoopResult:
        """Execute a validated request without blocking the caller's event loop."""
        return await run_loop(
            self.prepare(request), invoke=self._invoke, verify=self._verify
        )

    async def reserve(self, request: RunRequest) -> tuple[LoopConfig, RunPaths]:
        """Validate and allocate durable run artifacts before execution starts."""
        config = self.prepare(request)
        return config, await asyncio.to_thread(initialize_run, config, queued=True)

    async def run_reserved(self, config: LoopConfig, paths: RunPaths) -> LoopResult:
        """Execute a run whose directory and initial manifest already exist."""
        return await run_loop(
            config, invoke=self._invoke, verify=self._verify, paths=paths
        )
