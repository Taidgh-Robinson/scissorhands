"""Agent-specific command construction and completion-output handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class AgentAdapter(Protocol):
    """The small interface needed by the backend-neutral loop."""

    @property
    def name(self) -> str: ...

    @property
    def uses_stdin(self) -> bool: ...

    def command(
        self,
        *,
        executable: str,
        root: Path,
        final_message: Path,
        model: str | None,
        auto_approve: bool,
        prompt: str,
    ) -> list[str]: ...

    def completion_output(self, *, log: Path, final_message: Path) -> str: ...


@dataclass(frozen=True, slots=True)
class CodexAdapter:
    """Build Codex commands and read their final response."""

    name: str = "codex"
    uses_stdin: bool = True

    def command(
        self,
        *,
        executable: str,
        root: Path,
        final_message: Path,
        model: str | None,
        auto_approve: bool,
        prompt: str,
    ) -> list[str]:
        del prompt
        command = [
            executable,
            "exec",
            "--cd",
            str(root),
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
            "--output-last-message",
            str(final_message),
        ]
        if model:
            command.extend(["--model", model])
        if auto_approve:
            command.append("--approve-for-me")
        command.append("-")
        return command

    def completion_output(self, *, log: Path, final_message: Path) -> str:
        if final_message.exists():
            return final_message.read_text(encoding="utf-8")
        return log.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class OpenCodeAdapter:
    """Build OpenCode commands and read their combined output."""

    name: str = "opencode"
    uses_stdin: bool = False

    def command(
        self,
        *,
        executable: str,
        root: Path,
        final_message: Path,
        model: str | None,
        auto_approve: bool,
        prompt: str,
    ) -> list[str]:
        del root, final_message
        command = [executable, "run"]
        if model:
            command.extend(["--model", model])
        if auto_approve:
            command.append("--auto")
        command.append(prompt)
        return command

    def completion_output(self, *, log: Path, final_message: Path) -> str:
        del final_message
        return log.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class ClaudeCodeAdapter:
    """Build Claude Code print-mode commands and read their final response."""

    name: str = "claude"
    uses_stdin: bool = True

    def command(
        self,
        *,
        executable: str,
        root: Path,
        final_message: Path,
        model: str | None,
        auto_approve: bool,
        prompt: str,
    ) -> list[str]:
        del root, final_message, prompt
        command = [executable, "--print", "--output-format", "text"]
        if model:
            command.extend(["--model", model])
        if auto_approve:
            command.extend(["--permission-mode", "auto"])
        return command

    def completion_output(self, *, log: Path, final_message: Path) -> str:
        del final_message
        return log.read_text(encoding="utf-8")


ADAPTERS: dict[str, AgentAdapter] = {
    "claude": ClaudeCodeAdapter(),
    "codex": CodexAdapter(),
    "opencode": OpenCodeAdapter(),
}


def get_adapter(name: str) -> AgentAdapter:
    """Return a named adapter."""
    return ADAPTERS[name]
