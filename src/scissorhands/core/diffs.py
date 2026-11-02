"""Capture per-loop worktree changes without touching the user's Git index."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def _git(root: Path, *args: str, index: Path | None = None) -> str:
    env = os.environ.copy()
    if index is not None:
        env["GIT_INDEX_FILE"] = str(index)
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout


def snapshot_worktree(root: Path) -> str | None:
    """Write a Git tree for tracked and non-ignored new files at this instant."""
    try:
        if _git(root, "rev-parse", "--is-inside-work-tree").strip() != "true":
            return None
    except (OSError, subprocess.CalledProcessError):
        return None
    with TemporaryDirectory(prefix="scissorhands-index-") as directory:
        index = Path(directory) / "index"
        try:
            _git(root, "read-tree", "HEAD", index=index)
        except subprocess.CalledProcessError:
            _git(root, "read-tree", "--empty", index=index)
        _git(root, "add", "-A", "--", ".", index=index)
        _git(
            root,
            "rm",
            "--cached",
            "-r",
            "-q",
            "--ignore-unmatch",
            "--",
            ".scissorhands",
            index=index,
        )
        return _git(root, "write-tree", index=index).strip()


def write_loop_diff(root: Path, before: str, after: str, path: Path) -> None:
    """Save the patch between two worktree snapshots, including binary changes."""
    patch = _git(root, "diff", "--binary", "--no-ext-diff", "--no-color", before, after)
    path.write_text(patch, encoding="utf-8")
