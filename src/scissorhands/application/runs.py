"""Prepare and execute runs for any application interface."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from scissorhands.agents import ADAPTERS, get_adapter
from scissorhands.application.models import RunPreview, RunRequest
from scissorhands.core.loop.iteration import build_iteration
from scissorhands.core.loop.models import Invoke, LoopConfig, LoopResult, Verify
from scissorhands.core.loop.observer import RunObserver
from scissorhands.core.loop.runner import run_loop
from scissorhands.core.loop.verification import run_verification
from scissorhands.prompting.contract import default_contract, load_contract
from scissorhands.storage.paths import RunPaths
from scissorhands.storage.runs import initialize_run
from scissorhands.storage.work_items import load_work_item


class RunService:
    """Validate requests and delegate execution to the loop core.

    The service is silent unless an observer is supplied. CLI and API clients
    share these operations without depending on each other's presentation code.
    """

    def __init__(
        self,
        root: Path,
        *,
        invoke: Invoke | None = None,
        verify: Verify = run_verification,
        find_executable: Callable[[str], str | None] = shutil.which,
        observer: RunObserver | None = None,
    ) -> None:
        self.root = root.expanduser().resolve()
        self._invoke = invoke
        self._verify = verify
        self._find_executable = find_executable
        self._observer = observer

    def prepare(self, request: RunRequest) -> LoopConfig:
        """Resolve a request into validated, backend-neutral loop configuration."""
        self._validate_request(request)
        work_item_path = self._project_path(request.work_item_path)
        if not work_item_path.is_file():
            raise ValueError(f"Work item does not exist: {work_item_path}")
        executable = self._resolve_executable(request)
        work_item = load_work_item(work_item_path)
        contract = self._load_contract(request.contract_path)
        return LoopConfig(
            root=self.root,
            work_item=work_item,
            contract=contract,
            adapter=get_adapter(request.agent),
            executable=executable,
            max_iterations=request.max_iterations,
            model=request.model,
            auto_approve=request.auto_approve,
            work_item_path=work_item_path,
        )

    def _validate_request(self, request: RunRequest) -> None:
        if not self.root.is_dir():
            raise ValueError(
                f"Project root does not exist or is not a directory: {self.root}"
            )
        if request.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if request.agent not in ADAPTERS:
            raise ValueError(f"Unknown agent: {request.agent}")

    def _project_path(self, path: Path) -> Path:
        return path if path.is_absolute() else self.root / path

    def _resolve_executable(self, request: RunRequest) -> str:
        executable = request.executable or request.agent
        resolved = self._find_executable(executable)
        if resolved is None:
            raise ValueError(f"Agent executable not found: {executable}")
        return resolved

    def _load_contract(self, path: Path | None) -> str:
        if path is None:
            return default_contract()
        return load_contract(self._project_path(path))

    def preview(self, request: RunRequest) -> RunPreview:
        """Build the first command and prompt without writing files."""
        config = self.prepare(request)
        loop_dir = (
            self.root
            / ".scissorhands"
            / config.work_item.id
            / "run-DRY-RUN"
            / "loop-0001"
        )
        prepared = build_iteration(config, loop_dir, number=1, feedback=None)
        return RunPreview(
            tuple(prepared.command), prepared.prompt, config.adapter.uses_stdin
        )

    async def run(self, request: RunRequest) -> LoopResult:
        """Execute a request without blocking the caller's event loop."""
        return await run_loop(
            self.prepare(request),
            invoke=self._invoke,
            verify=self._verify,
            observer=self._observer,
        )

    async def reserve(self, request: RunRequest) -> tuple[LoopConfig, RunPaths]:
        """Validate and allocate a durable run ID before execution starts."""
        config = self.prepare(request)
        paths = await asyncio.to_thread(initialize_run, config, queued=True)
        return config, paths

    async def run_reserved(self, config: LoopConfig, paths: RunPaths) -> LoopResult:
        """Execute a run whose initial manifest and directory already exist."""
        return await run_loop(
            config,
            invoke=self._invoke,
            verify=self._verify,
            paths=paths,
            observer=self._observer,
        )
