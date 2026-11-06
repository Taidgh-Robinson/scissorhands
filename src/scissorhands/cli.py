"""Command-line interface for Scissorhands."""

from __future__ import annotations

import argparse
import asyncio
import shlex
from pathlib import Path

from scissorhands.agents import ADAPTERS
from scissorhands.core.run_service import RunRequest, RunService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scissorhands",
        description="Run a bounded, fresh-session agent loop with Claude Code, Codex, or OpenCode.",
    )
    parser.add_argument("--agent", choices=sorted(ADAPTERS), default="codex")
    parser.add_argument(
        "--work-item",
        type=Path,
        default=Path("WORK_ITEM.toml"),
        help="Path to a structured TOML work item (default: WORK_ITEM.toml)",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        help="Path to a custom iteration contract template (default: the built-in one)",
    )
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--model", help="Backend-specific model name")
    parser.add_argument("--executable", help="Override the selected agent executable")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Allow the backend to auto-approve tool permissions (review safety notes first)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print command and prompt, then exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = RunService(Path.cwd())
    request = RunRequest(
        work_item_path=args.work_item,
        agent=args.agent,
        max_iterations=args.max_iterations,
        model=args.model,
        executable=args.executable,
        auto_approve=args.auto_approve,
        contract_path=args.contract,
    )
    try:
        if args.dry_run:
            preview = service.preview(request)
        else:
            result = asyncio.run(service.run(request))
    except ValueError as error:
        raise SystemExit(str(error)) from error

    if args.dry_run:
        print("Command:")
        display_command = (
            preview.command
            if preview.uses_stdin
            else (*preview.command[:-1], "<PROMPT>")
        )
        print(shlex.join(display_command))
        print("\nPrompt:\n")
        print(preview.prompt)
        return 0

    if result.completed:
        print(
            f"\nScissorhands completed after {result.iterations} iteration(s). "
            f"Logs: {result.run_dir}"
        )
        return 0
    if result.failed:
        return 1
    print(f"\nIteration limit reached without completion. Logs: {result.run_dir}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
