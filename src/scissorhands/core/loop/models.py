"""Configuration, results, and callback types for loop execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scissorhands.agents import AgentAdapter
from scissorhands.core.verification import VerificationResult
from scissorhands.core.work_items import WorkItem
from scissorhands.prompting.contract import default_contract

DEFAULT_COMPLETION_MARKER = "<promise>COMPLETE</promise>"


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


@dataclass(frozen=True, slots=True)
class PreparedIteration:
    number: int
    prompt: str
    command: list[str]
    log: Path
    final_message: Path


Invoke = Callable[[list[str], str | None, Path, Path], int | Awaitable[int]]
Verify = Callable[
    [Sequence[str], Path], VerificationResult | Awaitable[VerificationResult]
]
