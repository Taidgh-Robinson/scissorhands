"""Framework-independent inputs and previews for run operations."""

from dataclasses import dataclass
from pathlib import Path


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
