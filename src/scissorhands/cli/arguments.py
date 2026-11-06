"""Parse terminal options without executing a run."""

import argparse
from pathlib import Path

from scissorhands.agents import ADAPTERS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scissorhands",
        description="Run a bounded, fresh-session agent loop with Claude Code, Codex, or OpenCode.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project folder for execution and relative paths (default: current directory)",
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
